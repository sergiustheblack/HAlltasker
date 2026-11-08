# HAlltasker v2 Changelog

## v2.0.0 - Initial Release

### Major Changes
- Complete rewrite from v1.3 with breaking changes
- New modular architecture with explicit plugin system
- ConfigEntry-based credential management
- Enhanced security features including secret redaction  
- Comprehensive test coverage including unit, integration, and end-to-end tests
- Modern web panel interface with status monitoring

### Key Features Added
- **Plugin System**: Modular plugin architecture supporting multiple task sources/destinations
- **Enhanced Security**: Defense-in-depth for secret values with proper redaction before errors cross into core 
- **Modern UI**: Complete reimplementation of the web panel
- **Improved Diagnostics**: Enhanced diagnostic capabilities with sensitive data redaction
- **Comprehensive Testing**: Extensive test coverage across all system components

### Architecture Improvements
- **Core Components**: Separation of concerns with dedicated modules for engine, plugins, configuration, and UI 
- **Configuration Store**: Advanced configuration management with subentry support
- **Link Store Schema 3**: Improved link persistence and schema compatibility handling  
- **Synchronization Engine**: Enhanced conflict resolution and change detection algorithms

### Migration Notes
This version contains breaking changes from v1.3:
- YAML configuration format changes
- Complete reimplementation of core logic and engine
- New plugin architecture and credential handling
- Web panel UI redesign
- Enhanced error handling and diagnostics

All existing v1.3 configurations will require manual migration to the new format.