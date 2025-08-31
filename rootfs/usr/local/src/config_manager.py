#!/usr/bin/env python3
"""
Configuration manager for dynamic Mosquitto configuration generation
"""
import json
import argparse
import logging
from pathlib import Path
from jinja2 import Template, Environment, FileSystemLoader

logger = logging.getLogger(__name__)


def load_addon_config(config_path: str) -> dict:
    """Load Home Assistant add-on configuration"""
    try:
        with open(config_path, 'r') as f:
            config = json.load(f)
        logger.info(f"Loaded configuration from {config_path}")
        return config
    except Exception as e:
        logger.error(f"Failed to load config from {config_path}: {e}")
        return {}


def generate_mosquitto_config(template_path: str, output_path: str, 
                            config: dict, certs_dir: str) -> bool:
    """
    Generate Mosquitto configuration from Jinja2 template
    
    Args:
        template_path: Path to the Jinja2 template file
        output_path: Path where the generated config will be written
        config: Add-on configuration dictionary
        certs_dir: Directory containing SSL certificates
        
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        # Load template
        template_dir = Path(template_path).parent
        template_name = Path(template_path).name
        
        env = Environment(loader=FileSystemLoader(str(template_dir)))
        template = env.get_template(template_name)
        
        # Prepare template variables
        template_vars = {
            'mqtt_broker_host': config.get('mqtt_broker_host', 'core-mosquitto'),
            'mqtt_broker_port': config.get('mqtt_broker_port', 1883),
            'mqtt_username': config.get('mqtt_username', ''),
            'mqtt_password': config.get('mqtt_password', ''),
            'mqtt_ssl': config.get('mqtt_ssl', False),
            'enable_bridge': config.get('enable_bridge', True),
            'certs_dir': certs_dir,
            'log_level': config.get('log_level', 'info').upper()
        }
        
        # Render template
        rendered_config = template.render(**template_vars)
        
        # Write generated configuration
        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)
        
        with open(output_path, 'w') as f:
            f.write(rendered_config)
        
        logger.info(f"Generated Mosquitto configuration: {output_path}")
        logger.info(f"Bridge enabled: {template_vars['enable_bridge']}")
        logger.info(f"Target broker: {template_vars['mqtt_broker_host']}:{template_vars['mqtt_broker_port']}")
        
        return True
        
    except Exception as e:
        logger.error(f"Failed to generate Mosquitto config: {e}")
        return False


def create_password_file(config: dict, output_dir: str) -> bool:
    """
    Create Mosquitto password file if authentication is enabled
    
    Args:
        config: Add-on configuration dictionary
        output_dir: Directory to write the password file
        
    Returns:
        bool: True if successful or not needed, False if failed
    """
    username = config.get('mqtt_username', '')
    password = config.get('mqtt_password', '')
    
    if not username or not password:
        logger.info("No MQTT authentication configured, skipping password file")
        return True
    
    try:
        import subprocess
        
        passwd_file = Path(output_dir) / "passwd"
        
        # Create password file using mosquitto_passwd
        cmd = ['mosquitto_passwd', '-c', str(passwd_file), username]
        
        # Run mosquitto_passwd with password input
        process = subprocess.run(
            cmd, 
            input=f"{password}\n{password}\n", 
            text=True, 
            capture_output=True
        )
        
        if process.returncode == 0:
            logger.info(f"Created password file: {passwd_file}")
            return True
        else:
            logger.error(f"mosquitto_passwd failed: {process.stderr}")
            
            # Fallback: create simple password file
            # Note: This is less secure, consider using mosquitto_passwd in production
            with open(passwd_file, 'w') as f:
                f.write(f"{username}:{password}\n")
            
            logger.warning("Created simple password file (less secure)")
            return True
            
    except Exception as e:
        logger.error(f"Failed to create password file: {e}")
        return False


def validate_config(config: dict) -> bool:
    """
    Validate add-on configuration
    
    Args:
        config: Configuration dictionary to validate
        
    Returns:
        bool: True if configuration is valid
    """
    required_fields = []  # No strictly required fields for basic operation
    
    for field in required_fields:
        if field not in config:
            logger.error(f"Missing required configuration field: {field}")
            return False
    
    # Validate port numbers
    mqtt_port = config.get('mqtt_broker_port', 1883)
    if not isinstance(mqtt_port, int) or not (1 <= mqtt_port <= 65535):
        logger.error(f"Invalid MQTT broker port: {mqtt_port}")
        return False
    
    # Validate boolean fields
    bool_fields = ['mqtt_ssl', 'enable_bridge']
    for field in bool_fields:
        if field in config and not isinstance(config[field], bool):
            logger.error(f"Field {field} must be boolean")
            return False
    
    # Validate log level
    valid_log_levels = ['debug', 'info', 'warning', 'error']
    log_level = config.get('log_level', 'info').lower()
    if log_level not in valid_log_levels:
        logger.error(f"Invalid log level: {log_level}")
        return False
    
    logger.info("Configuration validation passed")
    return True


def main():
    """Main entry point for configuration generation"""
    parser = argparse.ArgumentParser(description='Generate Mosquitto configuration')
    parser.add_argument('--template', required=True, help='Template file path')
    parser.add_argument('--output', required=True, help='Output configuration file path')
    parser.add_argument('--config', required=True, help='Add-on configuration JSON file')
    parser.add_argument('--certs-dir', required=True, help='Certificates directory')
    parser.add_argument('--verbose', action='store_true', help='Verbose logging')
    
    args = parser.parse_args()
    
    # Configure logging
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Load configuration
    config = load_addon_config(args.config)
    if not config:
        logger.error("Failed to load configuration")
        return 1
    
    # Validate configuration
    if not validate_config(config):
        logger.error("Configuration validation failed")
        return 1
    
    # Generate Mosquitto configuration
    success = generate_mosquitto_config(
        args.template, 
        args.output, 
        config, 
        args.certs_dir
    )
    
    if not success:
        logger.error("Failed to generate Mosquitto configuration")
        return 1
    
    # Create password file if needed
    output_dir = Path(args.output).parent
    if not create_password_file(config, output_dir):
        logger.warning("Failed to create password file")
        # Don't fail completely, authentication may not be needed
    
    logger.info("Configuration generation completed successfully")
    return 0


if __name__ == '__main__':
    exit(main())