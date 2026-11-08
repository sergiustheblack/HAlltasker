# HAlltasker v2 Documentation Style Guide

## Overview
This style guide provides consistent formatting and structure conventions for all documentation related to HAlltasker v2. All documentation should follow these guidelines for clarity and maintainability.

## File Structure

### Documentation Directory Organization
```
docs/v2/
├── README.md                 # High-level overview
├── SPEC_SUMMARY.md           # Complete specification summary  
├── ARCHITECTURE_OVERVIEW.md  # Complete architecture overview
├── PLUGINS.md                # Plugin system documentation
└── STYLE_GUIDE.md            # This document
```

## Formatting Conventions

### Headings
- Use consistent heading levels:
  - `#` for main sections
  - `##` for subsections  
  - `###` for sub-subsections
  - `####` for detailed items

### Code Examples
- Use triple backticks for code blocks:
```python
example_code_here()
```

### Lists and Bullets
- Use consistent bullet points:
  - **For key features**: 
    - Feature description
    - Additional details if needed

### Tables
- Use markdown table format for structured data:
| Column 1 | Column 2 |
|----------|----------|
| Content 1| Content 2|

## Terminology

### Core Concepts
- **Plugin**: A module that provides integration with specific task sources/destinations
- **Node**: An individual task source or destination within a connection  
- **Connection**: A configuration that defines a task source/destination and its credentials
- **Pair**: A synchronization rule between two nodes
- **Sync Cycle**: The process of reading from both nodes, detecting differences, and applying changes

### Technical Terms
- **CanonicalTask**: Standardized representation of a task with fields like title, description, status, due date
- **PluginRegistry**: System that manages registered plugins and their binding to nodes
- **LinkStore**: Storage system for synchronized task relationships 
- **ConfigStore**: Configuration management with revision tracking

## File Naming Conventions

### Documentation Files
- `README.md` - Main overview document
- `SPEC_SUMMARY.md` - Complete specification summary
- `ARCHITECTURE_OVERVIEW.md` - Detailed architecture documentation  
- `PLUGINS.md` - Plugin system documentation
- `STYLE_GUIDE.md` - This guide itself

### Code Documentation
- Use docstrings in Python files following Google style convention:
```python
def function_name(param1, param2):
    """Brief description of what the function does.
    
    Args:
        param1 (str): Description of param1
        param2 (int): Description of param2
    
    Returns:
        bool: Description of return value
    """
```

## Content Structure

### Architecture Documentation Template
```
# Component Name

## Overview
Brief description of the component's purpose and functionality

## Key Features
- Feature 1  
- Feature 2
- Feature 3

## Implementation Details
Technical details about how it works internally

## Configuration Examples
YAML or code examples showing configuration usage

## Error Handling
How errors are detected and handled within this component

## Related Components
Dependencies and interactions with other system components
```

### Plugin Documentation Template  
```
# Plugin Name

## Description
What the plugin integrates with and its primary purpose

## Features
- Supported operations (create, update, delete)
- Special capabilities or limitations

## Configuration
How to configure this plugin in YAML format

## Error Conditions
Special error cases this plugin might encounter

## Examples
Code examples showing usage patterns
```

## Versioning

### Documentation Versioning
All documentation should be versioned with the system version (e.g., v2.0, v2.1)

### Changes Tracking
When significant changes occur, document them in:
- `docs/v2/CHANGELOG.md` - if such a file exists
- Inline comments for code documentation  

## Review Process

### Documentation Review Checklist
- [ ] All components mentioned are properly documented
- [ ] Consistent terminology throughout  
- [ ] Examples match current implementation
- [ ] Technical accuracy verified
- [ ] No sensitive information disclosed
- [ ] Table of contents updated (if applicable)

This style guide ensures consistent, maintainable documentation that helps developers and users understand and work with HAlltasker v2 effectively.