import Foundation
import SwiftUI
import WebRTC

enum WebRTCConnectionState: Equatable {
  case disconnected
  case connecting
  case waitingForPeer
  case connected
  case backgrounded
  case error(String)
}

/// Orchestrates the WebRTC live streaming session: signaling, peer connection, and frame forwarding.
/// Supports multiple simultaneous viewers — each viewer gets its own WebRTCClient (RTCPeerConnection).
/// Follows the same @MainActor ObservableObject pattern as GeminiSessionViewModel.
@MainActor
class WebRTCSessionViewModel: ObservableObject {
  @Published var isActive: Bool = false
  @Published var connectionState: WebRTCConnectionState = .disconnected
  @Published var roomCode: String = ""
  @Published var isMuted: Bool = false
  @Published var errorMessage: String?
  @Published var remoteVideoTrack: RTCVideoTrack?
  @Published var hasRemoteVideo: Bool = false

  /// One WebRTCClient per viewer, keyed by viewerId
  private var peerConnections: [String: WebRTCClient] = [:]
  private var delegateAdapters: [String: WebRTCDelegateAdapter] = [:]
  private var signalingClient: SignalingClient?

  /// ICE servers fetched once and reused for all peer connections
  private var cachedIceServers: [RTCIceServer]?

  /// Saved room code for reconnecting after app backgrounding.
  private var savedRoomCode: String?
  private var foregroundObserver: Any?

  func startSession() async {
    guard !isActive else { return }
    guard WebRTCConfig.isConfigured else {
      errorMessage = "WebRTC signaling URL not configured."
      return
    }

    isActive = true
    connectionState = .connecting
    savedRoomCode = nil

    // Fetch TURN credentials for NAT traversal across networks
    cachedIceServers = await WebRTCConfig.fetchIceServers()

    connectSignaling(rejoinCode: nil)
    observeForeground()
  }

  func stopSession() {
    removeForegroundObserver()
    // Close ALL peer connections
    for (viewerId, client) in peerConnections {
      client.close()
      NSLog("[WebRTC] Closed peer connection for viewer %@", viewerId)
    }
    peerConnections.removeAll()
    delegateAdapters.removeAll()
    signalingClient?.disconnect()
    signalingClient = nil
    isActive = false
    connectionState = .disconnected
    roomCode = ""
    savedRoomCode = nil
    isMuted = false
    remoteVideoTrack = nil
    hasRemoteVideo = false
    cachedIceServers = nil
  }

  func toggleMute() {
    isMuted.toggle()
    for (_, client) in peerConnections {
      client.muteAudio(isMuted)
    }
  }

  /// Called by StreamSessionViewModel on each video frame.
  /// Pushes to ALL active peer connections.
  func pushVideoFrame(_ image: UIImage) {
    guard isActive, connectionState == .connected else { return }
    for (_, client) in peerConnections {
      client.pushVideoFrame(image)
    }
  }

  // MARK: - Peer Connection Management

  private func createPeerConnection(for viewerId: String) {
    // Close existing connection for this viewer if any
    if let existing = peerConnections[viewerId] {
      existing.close()
    }

    let client = WebRTCClient()
    let adapter = WebRTCDelegateAdapter(viewModel: self, viewerId: viewerId)
    delegateAdapters[viewerId] = adapter
    client.delegate = adapter
    client.setup(iceServers: cachedIceServers)
    peerConnections[viewerId] = client
    client.muteAudio(isMuted)
    NSLog("[WebRTC] Created peer connection for viewer %@", viewerId)
  }

  private func removePeerConnection(for viewerId: String) {
    if let client = peerConnections.removeValue(forKey: viewerId) {
      client.close()
      NSLog("[WebRTC] Removed peer connection for viewer %@", viewerId)
    }
    delegateAdapters.removeValue(forKey: viewerId)

    // Update connection state if no more viewers
    if peerConnections.isEmpty {
      connectionState = .waitingForPeer
    }
  }

  // MARK: - Signaling Setup

  private func connectSignaling(rejoinCode: String?) {
    signalingClient?.disconnect()

    let signaling = SignalingClient()
    signalingClient = signaling

    signaling.onConnected = { [weak self] in
      Task { @MainActor in
        if let code = rejoinCode {
          NSLog("[WebRTC] Reconnected, rejoining room: %@", code)
          self?.signalingClient?.rejoinRoom(code: code)
        } else {
          self?.signalingClient?.createRoom()
        }
      }
    }

    signaling.onMessageReceived = { [weak self] message in
      Task { @MainActor in
        self?.handleSignalingMessage(message)
      }
    }

    signaling.onDisconnected = { [weak self] reason in
      Task { @MainActor in
        guard let self, self.isActive else { return }
        // Don't fully stop -- mark as backgrounded so we can reconnect
        if self.savedRoomCode != nil {
          self.connectionState = .backgrounded
          NSLog("[WebRTC] Signaling disconnected (backgrounded), will rejoin: %@", reason ?? "unknown")
        } else {
          self.stopSession()
          self.errorMessage = "Signaling disconnected: \(reason ?? "Unknown")"
        }
      }
    }

    guard let url = URL(string: WebRTCConfig.signalingServerURL) else {
      errorMessage = "Invalid signaling URL"
      isActive = false
      connectionState = .disconnected
      return
    }
    signaling.connect(url: url)
  }

  // MARK: - Foreground Reconnect

  private func observeForeground() {
    removeForegroundObserver()
    foregroundObserver = NotificationCenter.default.addObserver(
      forName: UIApplication.willEnterForegroundNotification,
      object: nil,
      queue: .main
    ) { [weak self] _ in
      Task { @MainActor in
        self?.handleReturnToForeground()
      }
    }
  }

  private func removeForegroundObserver() {
    if let observer = foregroundObserver {
      NotificationCenter.default.removeObserver(observer)
      foregroundObserver = nil
    }
  }

  private func handleReturnToForeground() {
    guard isActive, let code = savedRoomCode else { return }
    NSLog("[WebRTC] App returned to foreground, reconnecting to room: %@", code)
    connectionState = .connecting

    // Tear down ALL old peer connections
    for (viewerId, client) in peerConnections {
      client.close()
    }
    peerConnections.removeAll()
    delegateAdapters.removeAll()
    remoteVideoTrack = nil
    hasRemoteVideo = false

    Task {
      cachedIceServers = await WebRTCConfig.fetchIceServers()
      connectSignaling(rejoinCode: code)
    }
  }

  // MARK: - Signaling Message Handling

  private func handleSignalingMessage(_ message: SignalingMessage) {
    switch message {
    case .roomCreated(let code):
      roomCode = code
      savedRoomCode = code
      connectionState = .waitingForPeer
      NSLog("[WebRTC] Room created: %@", code)

    case .roomRejoined(let code):
      roomCode = code
      savedRoomCode = code
      connectionState = .waitingForPeer
      NSLog("[WebRTC] Room rejoined: %@", code)

    case .peerJoined(let viewerId):
      NSLog("[WebRTC] Peer joined (viewerId: %@), creating offer", viewerId)
      createPeerConnection(for: viewerId)
      peerConnections[viewerId]?.createOffer { [weak self] sdp in
        self?.signalingClient?.send(sdp: sdp, viewerId: viewerId)
      }

    case .answer(let sdp, let viewerId):
      guard let viewerId, let client = peerConnections[viewerId] else {
        NSLog("[WebRTC] Answer received but no peer connection for viewerId: %@", viewerId ?? "nil")
        return
      }
      client.set(remoteSdp: sdp) { error in
        if let error {
          NSLog("[WebRTC] Error setting remote SDP for viewer %@: %@", viewerId, error.localizedDescription)
        }
      }

    case .candidate(let candidate, let viewerId):
      guard let viewerId, let client = peerConnections[viewerId] else {
        NSLog("[WebRTC] Candidate received but no peer connection for viewerId: %@", viewerId ?? "nil")
        return
      }
      client.set(remoteCandidate: candidate) { error in
        if let error {
          NSLog("[WebRTC] Error adding ICE candidate for viewer %@: %@", viewerId, error.localizedDescription)
        }
      }

    case .peerLeft(let viewerId):
      if let viewerId {
        NSLog("[WebRTC] Peer left (viewerId: %@)", viewerId)
        removePeerConnection(for: viewerId)
      } else {
        NSLog("[WebRTC] Peer left (no viewerId)")
        connectionState = .waitingForPeer
      }

    case .error(let msg):
      // If rejoin fails (room expired), fall back to creating a new room
      if savedRoomCode != nil && msg == "Room not found" {
        NSLog("[WebRTC] Rejoin failed (room expired), creating new room")
        savedRoomCode = nil
        signalingClient?.createRoom()
      } else {
        errorMessage = msg
      }

    case .roomJoined, .offer:
      break
    }
  }

  // MARK: - Connection State Updates (from WebRTCClient delegate, per viewer)

  fileprivate func handleConnectionStateChange(_ state: RTCIceConnectionState, viewerId: String) {
    switch state {
    case .connected, .completed:
      connectionState = .connected
      NSLog("[WebRTC] Peer connected (viewerId: %@)", viewerId)
    case .disconnected:
      // Only go to waitingForPeer if ALL peer connections are disconnected
      let anyConnected = peerConnections.values.contains { _ in true }
      if !anyConnected {
        connectionState = .waitingForPeer
      }
    case .failed:
      NSLog("[WebRTC] Peer connection failed (viewerId: %@)", viewerId)
      removePeerConnection(for: viewerId)
    case .closed:
      break
    default:
      break
    }
  }

  fileprivate func handleGeneratedCandidate(_ candidate: RTCIceCandidate, viewerId: String) {
    signalingClient?.send(candidate: candidate, viewerId: viewerId)
  }

  fileprivate func handleRemoteVideoTrackReceived(_ track: RTCVideoTrack, viewerId: String) {
    remoteVideoTrack = track
    hasRemoteVideo = true
    NSLog("[WebRTC] Remote video track received from viewer %@", viewerId)
  }

  fileprivate func handleRemoteVideoTrackRemoved(_ track: RTCVideoTrack, viewerId: String) {
    // Only clear if this was the currently displayed track
    if remoteVideoTrack === track {
      remoteVideoTrack = nil
      hasRemoteVideo = false
    }
    NSLog("[WebRTC] Remote video track removed from viewer %@", viewerId)
  }
}

// MARK: - Delegate Adapter (bridges nonisolated delegate to @MainActor ViewModel)
// Each viewer gets its own adapter instance that tags callbacks with viewerId.

private class WebRTCDelegateAdapter: WebRTCClientDelegate {
  private weak var viewModel: WebRTCSessionViewModel?
  private let viewerId: String

  init(viewModel: WebRTCSessionViewModel, viewerId: String) {
    self.viewModel = viewModel
    self.viewerId = viewerId
  }

  func webRTCClient(_ client: WebRTCClient, didChangeConnectionState state: RTCIceConnectionState) {
    let vid = viewerId
    Task { @MainActor [weak self] in
      self?.viewModel?.handleConnectionStateChange(state, viewerId: vid)
    }
  }

  func webRTCClient(_ client: WebRTCClient, didGenerateCandidate candidate: RTCIceCandidate) {
    let vid = viewerId
    Task { @MainActor [weak self] in
      self?.viewModel?.handleGeneratedCandidate(candidate, viewerId: vid)
    }
  }

  func webRTCClient(_ client: WebRTCClient, didReceiveRemoteVideoTrack track: RTCVideoTrack) {
    let vid = viewerId
    Task { @MainActor [weak self] in
      self?.viewModel?.handleRemoteVideoTrackReceived(track, viewerId: vid)
    }
  }

  func webRTCClient(_ client: WebRTCClient, didRemoveRemoteVideoTrack track: RTCVideoTrack) {
    let vid = viewerId
    Task { @MainActor [weak self] in
      self?.viewModel?.handleRemoteVideoTrackRemoved(track, viewerId: vid)
    }
  }
}
