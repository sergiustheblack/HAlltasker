# HAlltasker v2 Plugins

## Overview
HAlltasker v2 implements a modular plugin system that allows integration with various task management systems. Currently, it includes one built-in plugin for Home Assistant's native todo entities.

## Available Plugins

### 1. HaTodoPlugin (Built-in)
- **Description**: Integrates with Home Assistant's built-in `todo.*` entities
- **Features**:
  - Reads tasks from HA todo entities 
  - Writes tasks to HA todo entities
  - Supports task creation, update, and deletion
  - Handles due dates and descriptions
  - Respects HA entity capabilities for supported operations

### 2. Future Plugin Support
Based on the architecture specification, HAlltasker v2 is designed to support additional plugins for:
- CalDAV (with MKCALENDAR support)
- Yandex Tracker
- Jira 
- Other task management systems

## Plugin Interface

### Core Methods
All plugins must implement the following interface:

```python
class Plugin(ABC):
    def validate(self, connection_data: dict, secrets: dict) -> None:
        """Validate connection configuration and credentials"""
        
    async def containers(self, connection: dict, secrets: dict) -> list[Container]:
        """Discover available containers for this connection"""
        
    async def list(self, node: str) -> dict[str, CanonicalTask]:
        """Read tasks from the node"""
        
    async def create(self, node: str, task: CanonicalTask, known_ids: frozenset[str]) -> str:
        """Create a new task and return its external ID"""
        
    async def update(self, node: str, external_id: str, task: CanonicalTask, changed: frozenset[str]) -> None:
        """Update an existing task"""
        
    async def delete(self, node: str, external_id: str) -> None:
        """Delete a task"""
```

### Error Handling
Plugins should raise specific exceptions:
- `AuthFailed`: Authentication/authorization errors  
- `NodeUnavailable`: Temporary unavailability of the node
- `DependencyUnavailable`: Missing dependencies required for operations

## Plugin Registry
The system maintains a plugin registry that:
- Registers available plugins 
- Provides lookup by ID
- Handles binding of plugins to nodes with connection information
- Manages credential handling through subentries

## Configuration
Plugins are referenced in configuration using:
- `plugin` field specifying the plugin ID
- `credentials` section for credential management via HA ConfigEntry system

The plugin system supports both:
1. **Credential plugins**: Require user-provided credentials 
2. **Built-in plugins**: No credentials required (like HaTodoPlugin)

This design enables easy extension with new task sources and destinations while maintaining a consistent interface.