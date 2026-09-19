# Signing and notarizing NailQue

OTA and salon installs should use a signed macOS package. Unsigned builds still run in source mode (`python3 app.py`).

## macOS

1. Enroll in the Apple Developer Program and create a **Developer ID Application** certificate plus a **Developer ID Installer** certificate.
2. Build the pkg as usual:

   ```bash
   cd luxe-nails
   ./build-mac.sh
   ```

3. Sign the installer (replace the identity name with yours):

   ```bash
   productsign --sign "Developer ID Installer: Your Name (TEAMID)" \
     dist-installers/NailQue-macOS.pkg \
     dist-installers/NailQue-macOS-signed.pkg
   ```

4. Notarize with notarytool:

   ```bash
   xcrun notarytool submit dist-installers/NailQue-macOS-signed.pkg \
     --apple-id "you@example.com" \
     --team-id TEAMID \
     --keychain-profile "nailque-notary" \
     --wait
   xcrun stapler staple dist-installers/NailQue-macOS-signed.pkg
   ```

Store the API key / app-specific password in GitHub Actions secrets if you later add a notarize step. Do not commit certificates.

## Windows

Sign `NailQue-Setup.exe` with a standard Authenticode certificate (`signtool sign /fd SHA256 ...`) so SmartScreen does not warn on first launch.

## LAN HTTPS

NailQue can serve the desk and phones over TLS without a public reverse proxy.

```bash
openssl req -x509 -newkey rsa:2048 -sha256 -days 825 -nodes \
  -keyout nailque-key.pem -out nailque-cert.pem \
  -subj "/CN=NailQue LAN"
```

Then in the runtime `.env`:

```bash
SSL_CERTFILE=/absolute/path/nailque-cert.pem
SSL_KEYFILE=/absolute/path/nailque-key.pem
```

Phones must trust the certificate (AirDrop/email the `.pem` or use a local CA). The mobile QR code switches to `https://` automatically when TLS is enabled.
