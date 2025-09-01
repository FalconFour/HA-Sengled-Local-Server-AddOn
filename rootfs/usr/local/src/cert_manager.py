#!/usr/bin/env python3
"""
Certificate management system for Sengled Local Server
Generates and manages CA and server certificates for MQTT SSL
"""
import os
import argparse
import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from cryptography import x509
from cryptography.x509.oid import NameOID
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.backends import default_backend

logger = logging.getLogger(__name__)


class CertificateManager:
    """Manages SSL certificates for the MQTT broker"""
    
    def __init__(self, output_dir: str):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # Certificate file paths
        self.ca_key_path = self.output_dir / "ca.key"
        self.ca_cert_path = self.output_dir / "ca.crt"
        self.server_key_path = self.output_dir / "server.key"
        self.server_cert_path = self.output_dir / "server.crt"
        
    def generate_ca_certificate(self, common_name: str = "Sengled Local CA", 
                               validity_days: int = 3650) -> bool:
        """
        Generate Certificate Authority (CA) certificate
        
        Args:
            common_name: Common name for the CA certificate
            validity_days: Certificate validity period in days
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            logger.info("Generating CA private key...")
            
            # Generate CA private key
            ca_private_key = rsa.generate_private_key(
                public_exponent=65537,
                key_size=2048,
                backend=default_backend()
            )
            
            # Create CA certificate
            logger.info(f"Creating CA certificate: {common_name}")
            
            subject = issuer = x509.Name([
                x509.NameAttribute(NameOID.COUNTRY_NAME, "US"),
                x509.NameAttribute(NameOID.STATE_OR_PROVINCE_NAME, "CA"),
                x509.NameAttribute(NameOID.LOCALITY_NAME, "Local"),
                x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Sengled Local Server"),
                x509.NameAttribute(NameOID.ORGANIZATIONAL_UNIT_NAME, "Certificate Authority"),
                x509.NameAttribute(NameOID.COMMON_NAME, common_name),
            ])
            
            ca_certificate = x509.CertificateBuilder().subject_name(
                subject
            ).issuer_name(
                issuer
            ).public_key(
                ca_private_key.public_key()
            ).serial_number(
                x509.random_serial_number()
            ).not_valid_before(
                datetime.utcnow()
            ).not_valid_after(
                datetime.utcnow() + timedelta(days=validity_days)
            ).add_extension(
                x509.SubjectKeyIdentifier.from_public_key(ca_private_key.public_key()),
                critical=False,
            ).add_extension(
                x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_private_key.public_key()),
                critical=False,
            ).add_extension(
                x509.BasicConstraints(ca=True, path_length=0),
                critical=True,
            ).add_extension(
                x509.KeyUsage(
                    key_cert_sign=True,
                    crl_sign=True,
                    digital_signature=False,
                    key_encipherment=False,
                    key_agreement=False,
                    data_encipherment=False,
                    content_commitment=False,
                    encipher_only=False,
                    decipher_only=False
                ),
                critical=True,
            ).sign(ca_private_key, hashes.SHA256(), default_backend())
            
            # Save CA private key
            with open(self.ca_key_path, "wb") as f:
                f.write(ca_private_key.private_bytes(
                    encoding=serialization.Encoding.PEM,
                    format=serialization.PrivateFormat.PKCS8,
                    encryption_algorithm=serialization.NoEncryption()
                ))
            
            # Save CA certificate
            with open(self.ca_cert_path, "wb") as f:
                f.write(ca_certificate.public_bytes(serialization.Encoding.PEM))
            
            # Set secure permissions
            os.chmod(self.ca_key_path, 0o600)
            os.chmod(self.ca_cert_path, 0o644)
            
            logger.info(f"CA certificate generated successfully: {self.ca_cert_path}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to generate CA certificate: {e}")
            return False
    
    def generate_server_certificate(self, common_name: str = "sengled.local",
                                   san_list: list = None, validity_days: int = 365,
                                   simple_mode: bool = False) -> bool:
        """
        Generate server certificate signed by the CA
        
        Args:
            common_name: Common name for the server certificate
            san_list: List of Subject Alternative Names (IPs, hostnames)
            validity_days: Certificate validity period in days
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            # Check if CA certificate exists
            if not self.ca_key_path.exists() or not self.ca_cert_path.exists():
                logger.error("CA certificate not found. Generate CA first.")
                return False
            
            logger.info("Loading CA certificate and key...")
            
            # Load CA private key
            with open(self.ca_key_path, "rb") as f:
                ca_private_key = serialization.load_pem_private_key(
                    f.read(),
                    password=None,
                    backend=default_backend()
                )
            
            # Load CA certificate
            with open(self.ca_cert_path, "rb") as f:
                ca_certificate = x509.load_pem_x509_certificate(
                    f.read(),
                    default_backend()
                )
            
            logger.info("Generating server private key...")
            
            # Generate server private key
            server_private_key = rsa.generate_private_key(
                public_exponent=65537,
                key_size=2048,
                backend=default_backend()
            )
            
            # Create server certificate
            logger.info(f"Creating server certificate: {common_name}")
            
            subject = x509.Name([
                x509.NameAttribute(NameOID.COUNTRY_NAME, "US"),
                x509.NameAttribute(NameOID.STATE_OR_PROVINCE_NAME, "CA"),
                x509.NameAttribute(NameOID.LOCALITY_NAME, "Local"),
                x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Sengled Local Server"),
                x509.NameAttribute(NameOID.ORGANIZATIONAL_UNIT_NAME, "MQTT Broker"),
                x509.NameAttribute(NameOID.COMMON_NAME, common_name),
            ])
            
            # Build certificate
            cert_builder = x509.CertificateBuilder().subject_name(
                subject
            ).issuer_name(
                ca_certificate.subject
            ).public_key(
                server_private_key.public_key()
            ).serial_number(
                x509.random_serial_number()
            ).not_valid_before(
                datetime.utcnow()
            ).not_valid_after(
                datetime.utcnow() + timedelta(days=validity_days)
            ).add_extension(
                x509.SubjectKeyIdentifier.from_public_key(server_private_key.public_key()),
                critical=False,
            ).add_extension(
                x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_private_key.public_key()),
                critical=False,
            ).add_extension(
                x509.BasicConstraints(ca=False, path_length=None),
                critical=True,
            )
            
            # Simple mode: minimal extensions like OpenSSL basic certs
            # Complex mode: full modern certificate with all extensions
            if not simple_mode:
                logger.info("Adding full certificate extensions for modern clients")
                cert_builder = cert_builder.add_extension(
                    x509.KeyUsage(
                        key_cert_sign=False,
                        crl_sign=False,
                        digital_signature=True,
                        key_encipherment=True,
                        key_agreement=False,
                        data_encipherment=False,
                        content_commitment=False,
                        encipher_only=False,
                        decipher_only=False
                    ),
                    critical=True,
                ).add_extension(
                    x509.ExtendedKeyUsage([
                        x509.oid.ExtendedKeyUsageOID.SERVER_AUTH,
                    ]),
                    critical=True,
                )
                
                # Add Subject Alternative Names
                if san_list is None:
                    san_list = [
                        "localhost",
                        "sengled.local",
                        "127.0.0.1",
                        "::1"
                    ]
                
                # Convert SAN list to x509 objects
                san_objects = []
                for san in san_list:
                    try:
                        # Try to parse as IP address
                        import ipaddress
                        ip = ipaddress.ip_address(san)
                        san_objects.append(x509.IPAddress(ip))
                    except ValueError:
                        # Treat as DNS name
                        san_objects.append(x509.DNSName(san))
                
                if san_objects:
                    cert_builder = cert_builder.add_extension(
                        x509.SubjectAlternativeName(san_objects),
                        critical=False,
                    )
                    logger.info(f"Added SAN entries: {san_list}")
            else:
                logger.info("Using simplified certificate mode for legacy client compatibility")
            
            # Sign the certificate
            server_certificate = cert_builder.sign(
                ca_private_key, hashes.SHA256(), default_backend()
            )
            
            # Save server private key
            with open(self.server_key_path, "wb") as f:
                f.write(server_private_key.private_bytes(
                    encoding=serialization.Encoding.PEM,
                    format=serialization.PrivateFormat.PKCS8,
                    encryption_algorithm=serialization.NoEncryption()
                ))
            
            # Save server certificate
            with open(self.server_cert_path, "wb") as f:
                f.write(server_certificate.public_bytes(serialization.Encoding.PEM))
            
            # Set secure permissions
            os.chmod(self.server_key_path, 0o600)
            os.chmod(self.server_cert_path, 0o644)
            
            logger.info(f"Server certificate generated successfully: {self.server_cert_path}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to generate server certificate: {e}")
            return False
    
    def certificates_exist(self) -> bool:
        """Check if all required certificates exist"""
        required_files = [
            self.ca_cert_path,
            self.ca_key_path,
            self.server_cert_path,
            self.server_key_path
        ]
        
        return all(f.exists() for f in required_files)
    
    def get_certificate_info(self) -> dict:
        """Get information about existing certificates"""
        info = {
            "ca_exists": self.ca_cert_path.exists(),
            "server_exists": self.server_cert_path.exists(),
            "ca_cert_path": str(self.ca_cert_path),
            "server_cert_path": str(self.server_cert_path)
        }
        
        try:
            if self.ca_cert_path.exists():
                with open(self.ca_cert_path, "rb") as f:
                    ca_cert = x509.load_pem_x509_certificate(f.read(), default_backend())
                    info["ca_subject"] = ca_cert.subject.rfc4514_string()
                    info["ca_not_after"] = ca_cert.not_valid_after.isoformat()
                    info["ca_serial"] = str(ca_cert.serial_number)
            
            if self.server_cert_path.exists():
                with open(self.server_cert_path, "rb") as f:
                    server_cert = x509.load_pem_x509_certificate(f.read(), default_backend())
                    info["server_subject"] = server_cert.subject.rfc4514_string()
                    info["server_not_after"] = server_cert.not_valid_after.isoformat()
                    info["server_serial"] = str(server_cert.serial_number)
                    
                    # Extract SAN information
                    try:
                        san_ext = server_cert.extensions.get_extension_for_oid(
                            x509.oid.ExtensionOID.SUBJECT_ALTERNATIVE_NAME
                        )
                        san_names = []
                        for name in san_ext.value:
                            san_names.append(str(name))
                        info["server_san"] = san_names
                    except x509.ExtensionNotFound:
                        info["server_san"] = []
        
        except Exception as e:
            logger.error(f"Failed to read certificate info: {e}")
            info["error"] = str(e)
        
        return info
    
    def generate_all_certificates(self, common_name: str = "sengled.local", 
                                san_list: list = None, simple_mode: bool = True) -> bool:
        """
        Generate complete certificate chain (CA + server)
        
        Args:
            common_name: Common name for server certificate
            san_list: Subject Alternative Names for server certificate
            simple_mode: Use simple certificates for legacy client compatibility (default True for Sengled)
            
        Returns:
            bool: True if successful, False otherwise
        """
        logger.info("Starting complete certificate generation...")
        logger.info(f"Certificate mode: {'Simple (legacy compatible)' if simple_mode else 'Full (modern)'}")
        
        # Generate CA certificate
        if not self.generate_ca_certificate():
            return False
        
        # Generate server certificate
        if not self.generate_server_certificate(common_name, san_list, simple_mode=simple_mode):
            return False
        
        logger.info("All certificates generated successfully!")
        return True


def main():
    """Main entry point for certificate management"""
    parser = argparse.ArgumentParser(description='Manage SSL certificates for Sengled Local Server')
    parser.add_argument('--generate', action='store_true', help='Generate new certificates')
    parser.add_argument('--info', action='store_true', help='Show certificate information')
    parser.add_argument('--output-dir', required=True, help='Output directory for certificates')
    parser.add_argument('--common-name', default='sengled.local', help='Common name for server certificate')
    parser.add_argument('--san', action='append', help='Subject Alternative Name (can be used multiple times)')
    parser.add_argument('--simple', action='store_true', default=True, help='Generate simple certificates for legacy compatibility (default)')
    parser.add_argument('--full', action='store_true', help='Generate full certificates with all extensions')
    parser.add_argument('--verbose', action='store_true', help='Verbose logging')
    
    args = parser.parse_args()
    
    # Configure logging
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Create certificate manager
    cert_manager = CertificateManager(args.output_dir)
    
    if args.info:
        # Show certificate information
        info = cert_manager.get_certificate_info()
        print(json.dumps(info, indent=2, default=str))
        return 0
    
    if args.generate:
        # Generate certificates
        san_list = args.san if args.san else None
        # Use simple mode unless --full is explicitly specified
        simple_mode = not args.full
        success = cert_manager.generate_all_certificates(args.common_name, san_list, simple_mode=simple_mode)
        
        if success:
            logger.info("Certificate generation completed successfully")
            return 0
        else:
            logger.error("Certificate generation failed")
            return 1
    
    # Default: check if certificates exist
    if cert_manager.certificates_exist():
        logger.info("All certificates exist")
        return 0
    else:
        logger.warning("Some certificates are missing")
        return 1


if __name__ == '__main__':
    import json
    exit(main())