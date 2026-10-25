#!/bin/bash

# Setup MCP Servers Script
# This script installs and configures the required MCP servers

set -e

echo "🚀 Setting up MCP Servers for Healthcare AI Agent..."

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

print_header() {
    echo -e "${BLUE}[SETUP]${NC} $1"
}

# Check if Node.js and npm are installed
check_nodejs() {
    print_header "Checking Node.js installation..."
    if ! command -v node &> /dev/null; then
        print_error "Node.js is not installed. Please install Node.js first."
        exit 1
    fi
    
    if ! command -v npm &> /dev/null; then
        print_error "npm is not installed. Please install npm first."
        exit 1
    fi
    
    NODE_VERSION=$(node --version)
    NPM_VERSION=$(npm --version)
    print_status "Node.js version: $NODE_VERSION"
    print_status "npm version: $NPM_VERSION"
}

# Check if Python is installed
check_python() {
    print_header "Checking Python installation..."
    if ! command -v python3 &> /dev/null && ! command -v python &> /dev/null; then
        print_error "Python is not installed. Please install Python first."
        exit 1
    fi
    
    if command -v python3 &> /dev/null; then
        PYTHON_VERSION=$(python3 --version)
        print_status "Python version: $PYTHON_VERSION"
    else
        PYTHON_VERSION=$(python --version)
        print_status "Python version: $PYTHON_VERSION"
    fi
}

# Install Context7 MCP Server
install_context7() {
    print_header "Installing Context7 MCP Server..."
    
    # Check if Context7 is already available
    if npx --yes @upstash/context7-mcp --help &> /dev/null; then
        print_status "Context7 MCP Server is already available"
    else
        print_status "Installing Context7 MCP Server..."
        npx --yes @upstash/context7-mcp --help || {
            print_error "Failed to install Context7 MCP Server"
            exit 1
        }
    fi
    
    print_status "✅ Context7 MCP Server ready"
}

# Setup FHIR MCP Server
setup_fhir_mcp() {
    print_header "Setting up FHIR MCP Server..."
    
    if [ -d "fhir_mcp_server" ]; then
        print_status "FHIR MCP Server directory exists"
        
        # Install Python dependencies
        if [ -f "fhir_mcp_server/requirements.txt" ]; then
            print_status "Installing FHIR MCP Server dependencies..."
            pip3 install -r fhir_mcp_server/requirements.txt || {
                print_warning "Failed to install some FHIR MCP dependencies, continuing..."
            }
        fi
        
        print_status "✅ FHIR MCP Server ready"
    else
        print_warning "FHIR MCP Server directory not found, skipping..."
    fi
}

# Create MCP configuration files
create_mcp_configs() {
    print_header "Creating MCP configuration files..."
    
    # Create .cursor/mcp.json if it doesn't exist
    if [ ! -f "$HOME/.cursor/mcp.json" ]; then
        mkdir -p "$HOME/.cursor"
        cat > "$HOME/.cursor/mcp.json" << 'EOF'
{
  "mcpServers": {
    "context7": {
      "command": "npx",
      "args": [
        "-y",
        "@upstash/context7-mcp"
      ]
    }
  }
}
EOF
        print_status "Created Cursor MCP configuration"
    else
        print_status "Cursor MCP configuration already exists"
    fi
    
    print_status "✅ MCP configurations ready"
}

# Verify MCP servers
verify_mcp_servers() {
    print_header "Verifying MCP servers..."
    
    print_status "Testing Context7 MCP Server..."
    if timeout 10s npx --yes @upstash/context7-mcp --help &> /dev/null; then
        print_status "✅ Context7 MCP Server verified"
    else
        print_warning "⚠️  Context7 MCP Server verification failed or timed out"
    fi
}

# Main execution
main() {
    print_header "🏥 Healthcare AI Agent - MCP Servers Setup"
    echo
    
    check_nodejs
    check_python
    echo
    
    install_context7
    echo
    
    setup_fhir_mcp
    echo
    
    create_mcp_configs
    echo
    
    verify_mcp_servers
    echo
    
    print_status "🎉 MCP Servers setup completed successfully!"
    echo
    print_status "Next steps:"
    echo "  1. Configure your environment variables in .env file"
    echo "  2. For Context7: Set UPSTASH_REDIS_REST_URL and UPSTASH_REDIS_REST_TOKEN"
    echo "  3. Restart Cursor to load the new MCP servers"
    echo "  4. Test the MCP servers in your healthcare agents"
    echo
    print_status "Available MCP Servers:"
    echo "  • Context7: Enhanced context management and memory"
    echo "  • FHIR Healthcare: Local healthcare data management"
}

# Run main function
main "$@" 