# HAlltasker v2 Architecture Overview

## System Components

### 1. Core Engine Components

#### SyncEngine 
The central synchronization engine that processes sync cycles:
- Handles full read operations from both nodes
- Manages classification and conflict resolution
- Executes actions (create/update/delete)
- Manages link state and snapshots
- Coordinates with the plugin system for actual I/O operations

#### LinkStore (Schema 3)
Manages persistence of link state information:
- Stores synchronized task relationships between pairs
- Maintains metadata about pair contracts (binding, slots)
- Handles compatibility checks between versions
- Prevents old snapshots from being parsed under new semantics

#### ConfigStore  
Configuration management system with store persistence:
- YAML import/export capabilities
- Subentry flow integration for credentials
- Validation of configuration changes
- Revision tracking and conflict resolution

### 2. Plugin System  

#### Plugin Structure
- **PluginRegistry**: Central registry for all available plugins
- **Plugin Contract v2**: Defines interface for plugin operations:
  - `validate()`: Validates connection data
  - `containers()`: Discovers available containers 
  - `list()`: Reads tasks from source
  - `create()`, `update()`, `delete()`: Write operations
  - Error handling: `AuthFailed`, `NodeUnavailable`, `DependencyUnavailable`
- **Built-in Plugins**: Currently includes `HaTodoPlugin` for HA todo.* entities

#### PluginRegistry Functions
- `bind(node, connection, secrets)`: Creates BoundNode instances 
- `lookup(plugin_id)`: Finds plugin by ID
- Centralized management of plugin lifecycle and resources

### 3. Configuration and Flow Management

#### ConfigEntry System Integration  
- Uses Home Assistant's ConfigEntry subentries for credentials
- Credentials managed through dedicated flows:
  - New connection creation
  - Existing credential restoration  
  - Reconfiguration and rotation
- Automatic cleanup of stale credentials/subentries

#### YAML I/O Handling
- Import: Parses YAML configuration sections
- Validation: Static preflight + online validation 
- Export: Renders configuration with proper secret handling
- Startup import: Loads config only when store is empty  

### 4. User Interface and Services

#### Websocket API 
Complete set of administrative commands:
- `halltasker/plugins` - Get plugin descriptions  
- `halltasker/config/get` - Get current configuration
- `halltasker/config/save` - Save new configuration
- `halltasker/connections/containers` - List available containers
- `halltasker/nodes/fields` - Get field information for mapping
- `halltasker/pairs/dry_run` - Run simulation without side effects
- `halltasker/pairs/sync_now` - Trigger manual synchronization 
- `halltasker/status/subscribe` - Subscribe to sync status updates

#### Sensors and Services  
- Status sensors reporting last sync results per pair
- Manual service calls: `sync_now`, `dry_run`, `reload`
- Diagnostics system for troubleshooting

### 5. Runtime Management 

#### RuntimeSupervisor
- Manages administrative mutations (config changes, credential updates, link resets)
- Ensures serialization of operations to prevent race conditions
- Handles recovery from failures or interruptions
- Coordinates between multiple components with proper locking

#### SyncCoordinator  
- Schedules sync cycles based on configured intervals 
- Watches for relevant entity state changes
- Manages chain execution of related pairs
- Maintains status snapshot and subscribers  

### 6. Security Features

#### Credential Management
- Subentry flow integration for secure credential storage
- Automatic redaction of secrets before error propagation
- Protection against credential leakage through logging or events

#### Data Sanitization
- Redaction of secret values in logs, error messages, and diagnostics  
- Defense-in-depth for all boundary crossings between system components
- Protection against malicious data injection or information disclosure

### 7. Testing Infrastructure

Comprehensive test coverage:
- Core engine logic tests (engine, match, diff, conflict)  
- Plugin integration tests
- Configuration management tests
- Runtime and coordination tests
- Websocket API tests
- YAML I/O tests
- End-to-end system tests

## Data Flow

1. **Configuration loading**: 
   - Load store configuration or import from YAML
   - Validate credentials through plugin validation
   - Build runtime components (plugins, coordinator)

2. **Sync cycle execution**:
   - Read tasks from both nodes in pair  
   - Classify differences and detect conflicts
   - Plan actions based on conflict resolution rules
   - Execute planned actions with plugin I/O operations
   - Update link state and store results

3. **Status management**:
   - Record failure information for repairs
   - Publish status updates to subscribers
   - Generate diagnostics data for troubleshooting

## Configuration Structure

### Top-level YAML section:
```yaml
halltasker:
  connections:
    - id: <uuid>
      name: connection_name
      plugin: plugin_id  
      credentials: {...}
  nodes:
    - id: <uuid>
      name: node_name
      connection: connection_name
      container: {...}
  pairs: 
    - id: <uuid> 
      name: pair_name
      a: node_a
      b: node_b
      mapping: [ {...} ]
```

### Key Concepts:

- **Connections**: Task sources/destinations (plugins, credentials)
- **Nodes**: Individual task sources within connections  
- **Pairs**: Synchronization rules between two nodes
- **Mappings**: Field-to-field mapping definitions
- **Slots**: Canonical field names in the system
- **Link Store**: Persistence of synchronization state

## Error Handling and Diagnostics

- Comprehensive typed failures for different error conditions
- Aggregated failure reporting for repair/recovery systems  
- Secure diagnostics with sensitive data redaction
- Clear separation between user-facing errors and internal system errors
- Proper handling of authentication, dependency, and node failures

This architecture represents a significant improvement over the v1.3 implementation with better modularization, enhanced security features, and more robust error handling.