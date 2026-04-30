; retry.asm -- NASM x86-64 (Windows MS ABI). Retry helper.
;
; Public symbols:
;   do_fetch        -> rax = -1 (always fails in this benchmark)
;   fetch_with_retry(rcx=attempts) -> rax
;       Calls do_fetch up to `attempts` times. The "swallow":
;       returns rax = 0 (success-marker) when all attempts fail —
;       callers cannot tell what went wrong.
;
; Build (Windows): nasm -f win64 retry.asm -o retry.obj

bits 64
default rel

global do_fetch
global fetch_with_retry

section .text

; long do_fetch(void) — always returns -1
do_fetch:
    mov rax, -1
    ret

; long fetch_with_retry(long attempts /* rcx, MS x64 */)
;   - On success of any attempt: returns whatever do_fetch returned
;     (>= 0).
;   - On total failure: returns 0 (zero — the swallow).
;
; Stack: standard 32-byte shadow space allocated for the call to
; do_fetch per Windows x64 ABI.
fetch_with_retry:
    push rbx                ; preserve nonvolatile
    sub rsp, 32             ; shadow space for callee
    mov rbx, rcx            ; rbx = remaining attempts
.loop:
    test rbx, rbx
    jz .done
    call do_fetch
    test rax, rax
    jns .ret_success        ; rax >= 0 -> success path
    dec rbx
    jmp .loop
.done:
    xor rax, rax            ; swallow: return 0
.ret_success:
    add rsp, 32
    pop rbx
    ret
