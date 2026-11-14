#define _GNU_SOURCE
#include <stdio.h>
#include <string.h>
#include <unistd.h>
#include <errno.h>
#include <stdint.h>
#include <sched.h>
#include <sys/syscall.h>
#include <sys/socket.h>
#include <sys/mount.h>

static void out(const char *name, long ret) {
    int e = errno;
    if (ret >= 0) { printf("%s=ok\n", name); return; }
    printf("%s=errno:%d(%s)\n", name, e, strerror(e));
}

int main(void) {
    long r;

    errno = 0; r = syscall(SYS_socket, AF_VSOCK, SOCK_STREAM, 0); if (r >= 0) close(r);
    out("socket_vsock", r);

    errno = 0; r = syscall(SYS_io_uring_setup, 1, NULL);
    out("io_uring_setup", r);
    errno = 0; r = syscall(SYS_io_uring_enter, -1, 0, 0, 0, NULL, 0);
    out("io_uring_enter", r);
    errno = 0; r = syscall(SYS_io_uring_register, -1, 0, NULL, 0);
    out("io_uring_register", r);

    errno = 0; r = syscall(SYS_bpf, 0, NULL, 0);
    out("bpf", r);
    errno = 0; r = syscall(SYS_userfaultfd, 2 /* O_RDWR */);
    out("userfaultfd", r);
    errno = 0; r = syscall(SYS_perf_event_open, NULL, 0, 0, -1, 0);
    out("perf_event_open", r);

    errno = 0; r = syscall(SYS_keyctl, 1 /* KEYCTL_GET_KEYRING_ID */, 0, 0, 0, 0);
    out("keyctl", r);
    errno = 0; r = syscall(SYS_add_key, NULL, NULL, NULL, 0, 0);
    out("add_key", r);
    errno = 0; r = syscall(SYS_request_key, NULL, NULL, NULL, 0);
    out("request_key", r);
    errno = 0; r = syscall(SYS_syslog, 8, NULL, 0);
    out("syslog", r);

    errno = 0; r = syscall(SYS_kexec_load, 0, 0, 0, 0);
    out("kexec_load", r);
    errno = 0; r = syscall(SYS_kexec_file_load, -1, 0, 0, NULL, 0);
    out("kexec_file_load", r);
    errno = 0; r = syscall(SYS_init_module, NULL, 0, NULL);
    out("init_module", r);
    errno = 0; r = syscall(SYS_finit_module, -1, NULL, 0);
    out("finit_module", r);
    errno = 0; r = syscall(SYS_delete_module, NULL, 0);
    out("delete_module", r);
    errno = 0; r = syscall(SYS_reboot, 0, 0, 0, NULL);
    out("reboot", r);

    errno = 0; r = syscall(SYS_clock_settime, -1, NULL);
    out("clock_settime", r);
    errno = 0; r = syscall(SYS_clock_adjtime, -1, NULL);
    out("clock_adjtime", r);
    errno = 0; r = syscall(SYS_settimeofday, NULL, NULL);
    out("settimeofday", r);
    errno = 0; r = syscall(SYS_acct, NULL);
    out("acct", r);

    errno = 0; r = syscall(SYS_swapon, NULL, 0);
    out("swapon", r);
    errno = 0; r = syscall(SYS_swapoff, NULL);
    out("swapoff", r);
    errno = 0; r = syscall(SYS_quotactl, 0, NULL, 0, NULL);
    out("quotactl", r);
    errno = 0; r = syscall(SYS_mbind, NULL, 0, 0, NULL, 0, 0);
    out("mbind", r);
    errno = 0; r = syscall(SYS_set_mempolicy, 0, NULL, 0);
    out("set_mempolicy", r);
    errno = 0; r = syscall(SYS_migrate_pages, 0, 0, NULL, NULL);
    out("migrate_pages", r);
    errno = 0; r = syscall(SYS_move_pages, 0, 0, NULL, NULL, NULL, 0);
    out("move_pages", r);

    errno = 0; r = syscall(SYS_mount, NULL, NULL, NULL, 0, NULL);
    out("mount", r);
    errno = 0; r = syscall(SYS_umount2, NULL, 0);
    out("umount2", r);
    errno = 0; r = syscall(SYS_pivot_root, NULL, NULL);
    out("pivot_root", r);
    errno = 0; r = syscall(SYS_unshare, CLONE_NEWUSER);
    out("unshare_user", r);
    errno = 0; r = syscall(SYS_name_to_handle_at, 0, NULL, NULL, NULL, 0);
    out("name_to_handle_at", r);
    errno = 0; r = syscall(SYS_open_by_handle_at, -1, NULL, 0);
    out("open_by_handle_at", r);

    errno = 0; r = syscall(SYS_clone3, NULL, 0);
    out("clone3", r);

    return 0;
}
