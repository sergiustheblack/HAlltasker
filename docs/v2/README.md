# HAlltasker v2

## Overview

HAlltasker v2 is a major rewrite of the task synchronization integration for Home Assistant with enhanced architecture, security, and user experience. This document provides an overview of the key improvements and architectural changes.

## Key Features

### Enhanced Architecture
- **Modular Design**: Clear separation of concerns with dedicated modules for core logic, plugins, configuration, and UI.
- **Improved Extensibility**: Plugin architecture allows easy addition of new task sources and destinations.
- **Comprehensive Configuration Store**: Advanced configuration management with subentry support for credentials.

### Security Improvements
- **Enhanced Credential Handling**: Secure credential storage using Home Assistant's config entry system with proper redaction.
- **Defensive Programming**: Defense in-depth for secret values, including redaction before errors cross into core.
- **Input Sanitization**: Robust validation and sanitization throughout the pipeline to prevent security issues.

### User Experience Improvements
- **Modern Web Panel**: Enhanced user interface with better visualization of connections, nodes, and pairs.
- **Enhanced Diagnostics**: Improved diagnostic capabilities with sensitive data redaction.
- **Comprehensive Testing**: Extensive test coverage including unit tests, integration tests, and e2e tests.

## Architectural Components

1. **Core System**
   - Engine for synchronization cycles
   - Configuration store and management
   - Link storage with schema 3
   - Conflict resolution algorithms

2. ** Plugin System**
   - Modular plugins for different task sources/destinations
   - Credential handling and validation
   - Discovery mechanisms for containers

3. **User Interface**
   - Webpanel for configuration and monitoring
   - Sensors for status reporting
   - Services for manual synchronization and diagnostics

4. **Configuration and Storage**
   - YAML import/export capabilities
   - ConfigEntry-based subentries for credentials
   - Repair issues management

5. **Security Features**
   - Secret redaction before logging or error propagation
   - Secure credential storage
   - Data sanitization at boundaries

## Migration from v1

This version represents a complete rewrite with breaking changes from v1.3. Key migration considerations include:

- YAML configuration format changes
- Complete reimplementation of engine and core logic
- New plugin architecture and credential handling
- Webpanel UI redesign
- Enhanced error handling and diagnostics

The system now requires explicit credentials through Home Assistant's configuration entries rather than relying solely on direct configuration.