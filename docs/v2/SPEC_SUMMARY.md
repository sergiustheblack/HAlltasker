# HAlltasker v2 Specification Summary

## Overview
HAlltasker v2 is a complete rewrite of the task synchronization integration for Home Assistant, designed to provide better architectural separation, enhanced security, and improved extensibility.

## Core Architecture Components

### 1. Plugin System
- **Plugin Contract v2**: Defines how plugins interact with the system
- **Built-in Plugins**: 
  - `HaTodoPlugin`: Handles integration with Home Assistant's built-in todo entities
- **Extensible Design**: Supports creating new plugins for different task sources/destinations

### 2. Engine and Core Logic
- **SyncEngine**: Main synchronization engine that handles the core logic of task synchronization
- **Link Store**: Manages the storage of link state between synchronized tasks (schema version 3)
- **Configuration Store**: Handles configuration management with subentry support for credentials
- **PluginRegistry**: Registry for managing plugins

### 3. Configuration Management
- **YAML Import/Export**: Full support for importing and exporting configurations in YAML format  
- **Subentry Flow**: Credentials handled through Home Assistant's ConfigEntry subentries system
- **Repairs System**: Automatic tracking and reporting of connection issues

### 4. Web Interface
- **Web Panel**: Modern user interface for configuration and monitoring
- **Sensors**: Status reporting through Home Assistant sensors
- **Services**: Manual synchronization and dry-run capabilities

## Key Improvements Over v1.3

### Security Enhancements
- Enhanced credential handling with proper redaction before logging or error propagation
- Defense-in-depth for secret values including redaction before errors cross into core
- Secure credential storage through ConfigEntry system

### Architectural Improvements
- Modular design with clear separation between core logic, plugins, UI, and configuration
- Improved extensibility through plugin architecture
- Better error handling and diagnostics with sensitive data redaction

### User Experience
- Modern web panel with better visualization of connections, nodes, and pairs
- Comprehensive testing including end-to-end tests
- Enhanced diagnostics with secure data handling

## Key Files and Modules

### Core System Files:
- `custom_components/halltasker/__init__.py`: Main setup and service registration
- `custom_components/halltasker/coordinator.py`: Synchronization coordinator 
- `custom_components/halltasker/core/`: Core engine components
  - `engine.py`: Core synchronization engine
  - `link_store.py`: Link storage management
  - `model.py`: Data models
  - `schema_builder.py`: Schema building utilities 
  - `mapping.py`: Field mapping functionality

### Plugin Files:
- `custom_components/halltasker/plugins/ha_todo.py`: HaTodo plugin for todo.* entities
- `custom_components/halltasker/plugins/base.py`: Base plugin definitions
- `custom_components/halltasker/plugins/registry.py`: Plugin registry system

### Test Structure:
- `tests/core/`: Core logic tests
- `tests/plugins/`: Plugin-specific tests
- `tests/test_coordinator.py`: Coordinator tests
- End-to-end tests in `tests/test_e2e.py`

## Configuration Format

The YAML format includes:
- **Connections**: Task source/destination definitions with plugin types and credentials
- **Nodes**: Individual task sources or destinations within connections  
- **Pairs**: Configuration of synchronization between two nodes
- **Field Mapping**: Specification of how native fields map to canonical attributes

## Main Features

1. **Task Synchronization**: Keep tasks synchronized between different task sources/destinations
2. **Multiple Task Services**: Support for integration with various task systems (todo.* entities, CalDAV, Yandex Reminders)
3. **Conflict Resolution**: Advanced conflict detection and resolution
4. **Web Interface**: Comprehensive control panel through Home Assistant UI
5. **Security**: Secure credential handling and data sanitization

## Migration Notes

This v2 is a complete rewrite with breaking changes from v1.3:
- YAML format changes
- Complete reimplementation of core logic
- New plugin architecture
- Web panel redesign
- Enhanced error handling and diagnostics