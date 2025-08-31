#!/bin/bash
# Backup and deployment utilities for Sengled Local Server

set -e

# Configuration
BACKUP_DIR="/data/backups"
CONFIG_DIR="/data/config"
CERTS_DIR="/data/certs"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

log() {
    echo -e "[$(date '+%Y-%m-%d %H:%M:%S')] $1"
}

log_success() {
    log "${GREEN}✅ $1${NC}"
}

log_warning() {
    log "${YELLOW}⚠️  $1${NC}"
}

log_error() {
    log "${RED}❌ $1${NC}"
}

# Create backup directory
ensure_backup_dir() {
    mkdir -p "$BACKUP_DIR"
    log_success "Backup directory ready: $BACKUP_DIR"
}

# Backup configuration and certificates
backup_config() {
    log "Creating configuration backup..."
    
    local backup_file="$BACKUP_DIR/sengled_backup_$TIMESTAMP.tar.gz"
    
    # Create temporary directory for backup files
    local temp_dir=$(mktemp -d)
    
    # Copy configuration files
    if [ -d "$CONFIG_DIR" ]; then
        cp -r "$CONFIG_DIR" "$temp_dir/"
        log_success "Configuration files backed up"
    else
        log_warning "No configuration directory found"
    fi
    
    # Copy certificates
    if [ -d "$CERTS_DIR" ]; then
        cp -r "$CERTS_DIR" "$temp_dir/"
        log_success "Certificate files backed up"
    else
        log_warning "No certificates directory found"
    fi
    
    # Copy add-on options (if available)
    if [ -f "/data/options.json" ]; then
        cp "/data/options.json" "$temp_dir/"
        log_success "Add-on options backed up"
    fi
    
    # Create compressed archive
    tar -czf "$backup_file" -C "$temp_dir" .
    
    # Cleanup temporary directory
    rm -rf "$temp_dir"
    
    # Set secure permissions
    chmod 600 "$backup_file"
    
    log_success "Backup created: $backup_file"
    echo "$backup_file"
}

# Restore from backup
restore_config() {
    local backup_file="$1"
    
    if [ -z "$backup_file" ]; then
        log_error "Usage: $0 restore <backup_file>"
        return 1
    fi
    
    if [ ! -f "$backup_file" ]; then
        log_error "Backup file not found: $backup_file"
        return 1
    fi
    
    log "Restoring from backup: $backup_file"
    
    # Create temporary directory for extraction
    local temp_dir=$(mktemp -d)
    
    # Extract backup
    tar -xzf "$backup_file" -C "$temp_dir"
    
    # Restore configuration
    if [ -d "$temp_dir/config" ]; then
        mkdir -p "$CONFIG_DIR"
        cp -r "$temp_dir/config/"* "$CONFIG_DIR/"
        log_success "Configuration restored"
    fi
    
    # Restore certificates
    if [ -d "$temp_dir/certs" ]; then
        mkdir -p "$CERTS_DIR"
        cp -r "$temp_dir/certs/"* "$CERTS_DIR/"
        # Set proper permissions for certificates
        chmod 600 "$CERTS_DIR"/*.key 2>/dev/null || true
        chmod 644 "$CERTS_DIR"/*.crt 2>/dev/null || true
        log_success "Certificates restored"
    fi
    
    # Restore add-on options
    if [ -f "$temp_dir/options.json" ]; then
        cp "$temp_dir/options.json" "/data/options.json"
        log_success "Add-on options restored"
    fi
    
    # Cleanup
    rm -rf "$temp_dir"
    
    log_success "Restore completed successfully"
    log_warning "Restart the add-on to apply restored configuration"
}

# List available backups
list_backups() {
    log "Available backups in $BACKUP_DIR:"
    
    if [ ! -d "$BACKUP_DIR" ]; then
        log_warning "No backup directory found"
        return 0
    fi
    
    local count=0
    for backup in "$BACKUP_DIR"/sengled_backup_*.tar.gz; do
        if [ -f "$backup" ]; then
            local size=$(du -h "$backup" | cut -f1)
            local date=$(basename "$backup" .tar.gz | sed 's/sengled_backup_//' | sed 's/_/ /')
            echo "  📦 $(basename "$backup") ($size) - $date"
            count=$((count + 1))
        fi
    done
    
    if [ $count -eq 0 ]; then
        log_warning "No backups found"
    else
        log_success "Found $count backup(s)"
    fi
}

# Cleanup old backups (keep last 10)
cleanup_backups() {
    log "Cleaning up old backups..."
    
    if [ ! -d "$BACKUP_DIR" ]; then
        log_warning "No backup directory found"
        return 0
    fi
    
    # Count current backups
    local count=$(find "$BACKUP_DIR" -name "sengled_backup_*.tar.gz" | wc -l)
    
    if [ $count -le 10 ]; then
        log_success "No cleanup needed ($count backups, keeping up to 10)"
        return 0
    fi
    
    # Remove oldest backups, keep newest 10
    find "$BACKUP_DIR" -name "sengled_backup_*.tar.gz" -type f -printf '%T@ %p\n' | \
        sort -n | \
        head -n -10 | \
        cut -d' ' -f2- | \
        xargs rm -f
    
    local removed=$((count - 10))
    log_success "Removed $removed old backup(s), kept 10 newest"
}

# Export configuration for sharing (without certificates)
export_config() {
    log "Exporting shareable configuration..."
    
    local export_file="$BACKUP_DIR/sengled_config_export_$TIMESTAMP.json"
    
    # Create configuration export (sanitized)
    if [ -f "/data/options.json" ]; then
        # Remove sensitive data (passwords) before export
        jq 'del(.mqtt_password)' /data/options.json > "$export_file"
        log_success "Configuration exported (passwords removed): $export_file"
        echo "$export_file"
    else
        log_error "No configuration file found to export"
        return 1
    fi
}

# Validate backup integrity
validate_backup() {
    local backup_file="$1"
    
    if [ -z "$backup_file" ]; then
        log_error "Usage: $0 validate <backup_file>"
        return 1
    fi
    
    if [ ! -f "$backup_file" ]; then
        log_error "Backup file not found: $backup_file"
        return 1
    fi
    
    log "Validating backup: $backup_file"
    
    # Test if archive is valid
    if tar -tzf "$backup_file" >/dev/null 2>&1; then
        log_success "Archive integrity check passed"
    else
        log_error "Archive is corrupted or invalid"
        return 1
    fi
    
    # List contents
    log "Backup contents:"
    tar -tzf "$backup_file" | sed 's/^/  📄 /'
    
    log_success "Backup validation completed"
}

# Show help
show_help() {
    echo "Sengled Local Server - Backup & Deployment Utilities"
    echo ""
    echo "Usage: $0 <command> [options]"
    echo ""
    echo "Commands:"
    echo "  backup          Create a backup of configuration and certificates"
    echo "  restore <file>  Restore from a backup file"
    echo "  list            List available backups"
    echo "  cleanup         Remove old backups (keep 10 newest)"
    echo "  export          Export configuration for sharing (passwords removed)"
    echo "  validate <file> Validate backup file integrity"
    echo "  help            Show this help message"
    echo ""
    echo "Examples:"
    echo "  $0 backup"
    echo "  $0 restore /data/backups/sengled_backup_20250830_143000.tar.gz"
    echo "  $0 list"
    echo "  $0 cleanup"
}

# Main command dispatcher
main() {
    case "${1:-help}" in
        "backup")
            ensure_backup_dir
            backup_config
            cleanup_backups
            ;;
        "restore")
            restore_config "$2"
            ;;
        "list")
            list_backups
            ;;
        "cleanup")
            cleanup_backups
            ;;
        "export")
            ensure_backup_dir
            export_config
            ;;
        "validate")
            validate_backup "$2"
            ;;
        "help"|"--help"|"-h")
            show_help
            ;;
        *)
            log_error "Unknown command: $1"
            echo ""
            show_help
            exit 1
            ;;
    esac
}

# Check if script is being run directly
if [ "${BASH_SOURCE[0]}" == "${0}" ]; then
    main "$@"
fi