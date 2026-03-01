# YC_hackathon Development Patterns

> Auto-generated skill from repository analysis

## Overview

This skill covers development patterns for the YC_hackathon project, a Python-based research and intelligence gathering system with a TypeScript frontend. The codebase features a modular agent architecture, external service integrations, and comprehensive testing patterns. The system uses Convex for the database layer and follows Protocol-based design for service abstractions.

## Coding Conventions

### File Naming
- Use `snake_case` for Python files: `user_agent.py`, `api_client.py`
- Use `PascalCase` for React components: `UserProfile.tsx`, `DataTable.tsx`

### Python Import Style
```python
# Standard library imports first
import json
from typing import Protocol, Dict, Any

# Third-party imports
from pydantic import BaseModel, Field
import httpx

# Local imports
from .models import UserModel
from ..config import Settings
```

### Module Structure
```python
# Protocol definition in __init__.py
class ServiceProtocol(Protocol):
    async def fetch_data(self, query: str) -> Dict[str, Any]: ...

# Implementation in separate files
class ServiceClient:
    def __init__(self, settings: Settings):
        self.settings = settings
```

### Commit Messages
- Use conventional commits: `feat:`, `fix:`, `chore:`, `docs:`, `test:`, `ci:`
- Keep messages around 60 characters
- Example: `feat: add github research agent with rate limiting`

## Workflows

### Add New Agent
**Trigger:** When someone wants to add a new data source or research capability  
**Command:** `/new-agent`

1. Create new agent file in `backend/agents/{agent_name}_agent.py`
```python
from typing import Dict, Any
from ..config import Settings

class GitHubAgent:
    def __init__(self, settings: Settings):
        self.settings = settings
    
    async def research(self, query: str) -> Dict[str, Any]:
        # Implementation here
        pass
```

2. Update `backend/agents/__init__.py` to export the agent
```python
from .github_agent import GitHubAgent
from .twitter_agent import TwitterAgent
from .new_agent import NewAgent  # Add this line

__all__ = ["GitHubAgent", "TwitterAgent", "NewAgent"]
```

3. Add agent to orchestrator fan-out pattern in `backend/agents/orchestrator.py`
```python
async def coordinate_research(self, query: str) -> Dict[str, Any]:
    agents = [
        self.github_agent.research(query),
        self.twitter_agent.research(query),
        self.new_agent.research(query),  # Add this line
    ]
    results = await asyncio.gather(*agents)
```

4. Add configuration keys to `backend/config.py` if needed
```python
class Settings(BaseSettings):
    new_agent_api_key: str = Field(..., env="NEW_AGENT_API_KEY")
    new_agent_base_url: str = "https://api.service.com"
```

5. Write tests in `backend/tests/test_agents.py`
```python
@pytest.mark.asyncio
async def test_new_agent_research():
    with patch("httpx.AsyncClient.get") as mock_get:
        mock_get.return_value.json.return_value = {"result": "test"}
        agent = NewAgent(settings)
        result = await agent.research("test query")
        assert result["result"] == "test"
```

### Add Test Coverage
**Trigger:** When someone needs to test new functionality or fix broken tests  
**Command:** `/add-tests`

1. Create test file in `backend/tests/test_{module}.py`
```python
import pytest
from unittest.mock import patch, AsyncMock
from backend.module import ModuleClass

@pytest.fixture
def mock_settings():
    return Settings(api_key="test_key")
```

2. Add comprehensive fixtures and mocks
```python
@pytest.fixture
def mock_httpx_client():
    with patch("httpx.AsyncClient") as mock:
        mock.return_value.__aenter__.return_value.get = AsyncMock()
        yield mock
```

3. Mock external API calls
```python
@pytest.mark.asyncio
async def test_api_integration(mock_httpx_client):
    mock_response = AsyncMock()
    mock_response.json.return_value = {"data": "test"}
    mock_httpx_client.return_value.__aenter__.return_value.get.return_value = mock_response
```

4. Ensure coverage thresholds are met by testing edge cases and error conditions

5. Fix any ruff/lint violations that appear in CI

### Add Service Integration
**Trigger:** When someone wants to add a new external service or API integration  
**Command:** `/new-service`

1. Create Protocol interface in `backend/{module}/__init__.py`
```python
from typing import Protocol, Dict, Any

class ServiceProtocol(Protocol):
    async def fetch_data(self, query: str) -> Dict[str, Any]: ...
    async def validate_credentials(self) -> bool: ...
```

2. Add Pydantic models in `backend/{module}/models.py`
```python
from pydantic import BaseModel, Field
from typing import Optional

class ServiceResponse(BaseModel):
    id: str
    data: Dict[str, Any]
    timestamp: Optional[str] = None
```

3. Implement client class with Settings injection
```python
# backend/{module}/{service}_client.py
import httpx
from ..config import Settings
from .models import ServiceResponse

class ServiceClient:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.base_url = settings.service_base_url
        
    async def fetch_data(self, query: str) -> ServiceResponse:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{self.base_url}/data", params={"q": query})
            return ServiceResponse(**response.json())
```

4. Add configuration to `backend/config.py`
```python
class Settings(BaseSettings):
    service_api_key: str = Field(..., env="SERVICE_API_KEY")
    service_base_url: str = "https://api.service.com/v1"
    service_timeout: int = 30
```

5. Update `.env.example` with new environment variables
```bash
# Service Configuration
SERVICE_API_KEY=your_api_key_here
SERVICE_BASE_URL=https://api.service.com/v1
```

6. Add comprehensive tests with mocking patterns

### Update Convex Schema
**Trigger:** When database schema or Convex functions are modified  
**Command:** `/regen-schema`

1. Modify backend database operations as needed

2. Convex automatically regenerates type definitions in:
   - `frontend/convex/_generated/api.d.ts`
   - `frontend/convex/_generated/api.js`
   - `frontend/convex/_generated/dataModel.d.ts`
   - `frontend/convex/_generated/server.d.ts`
   - `frontend/convex/_generated/server.js`

3. Verify frontend TypeScript compilation succeeds with new types

4. Update any components using the modified schema

### Add Frontend Component Tests
**Trigger:** When new frontend components are created or need test coverage  
**Command:** `/test-component`

1. Create `__tests__` directory in components folder
```typescript
// frontend/src/components/__tests__/UserProfile.test.tsx
import { render, screen } from '@testing-library/react'
import { UserProfile } from '../UserProfile'
```

2. Write component test with React Testing Library
```typescript
describe('UserProfile', () => {
  it('renders user information correctly', () => {
    const mockUser = { name: 'John Doe', email: 'john@example.com' }
    render(<UserProfile user={mockUser} />)
    
    expect(screen.getByTestId('user-name')).toHaveTextContent('John Doe')
    expect(screen.getByTestId('user-email')).toHaveTextContent('john@example.com')
  })
})
```

3. Add data-testid attributes to components
```typescript
export const UserProfile = ({ user }: Props) => (
  <div>
    <h2 data-testid="user-name">{user.name}</h2>
    <p data-testid="user-email">{user.email}</p>
  </div>
)
```

4. Mock external dependencies and Convex hooks
```typescript
import { vi } from 'vitest'

vi.mock('../hooks/useConvex', () => ({
  useQuery: vi.fn(() => ({ data: mockData, loading: false }))
}))
```

5. Update `frontend/package.json` if new test dependencies are needed

## Testing Patterns

### Backend Testing
- Use `pytest` with async support
- Mock external API calls with `httpx` patches
- Create fixtures for common test data and settings
- Test both success and error conditions
- Maintain high coverage thresholds

### Frontend Testing
- Use Vitest with React Testing Library
- Test component rendering and user interactions
- Mock Convex queries and mutations
- Use `data-testid` attributes for reliable element selection
- Test accessibility and responsive behavior

## Commands

| Command | Purpose |
|---------|---------|
| `/new-agent` | Add a new research/intelligence gathering agent |
| `/add-tests` | Create comprehensive test coverage for modules |
| `/new-service` | Integrate external service with Protocol patterns |
| `/regen-schema` | Handle Convex schema regeneration workflow |
| `/test-component` | Add React component tests with Testing Library |