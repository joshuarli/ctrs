#define _GNU_SOURCE
#include <errno.h>
#include <linux/futex.h>
#include <sched.h>
#include <stdio.h>
#include <stdlib.h>
#include <sys/prctl.h>
#include <sys/stat.h>
#include <sys/syscall.h>
#include <time.h>
#include <unistd.h>

int main(int argc, char **argv) {
    if (argc != 3) return 2;
    char *end;
    long count = strtol(argv[2], &end, 10);
    if (*end || count < 1 || count > 10000) return 2;
    cpu_set_t cpus;
    CPU_ZERO(&cpus);
    CPU_SET(0, &cpus);
    if (sched_setaffinity(0, sizeof(cpus), &cpus) || prctl(PR_SET_NAME, argv[1], 0, 0, 0)) return 3;
    if (mkfifo("/tmp/np-futex-go", 0600)) return 4;
    FILE *go = fopen("/tmp/np-futex-go", "r");
    if (!go || fgetc(go) != 'G') return 5;
    fclose(go);
    int value = 0;
    struct timespec timeout = {.tv_sec = 0, .tv_nsec = 1};
    for (long i = 0; i < count; i++) {
        errno = 0;
        if (syscall(SYS_futex, &value, FUTEX_WAIT_PRIVATE, 1, NULL, NULL, 0) != -1 || errno != EAGAIN) return 6;
        if (syscall(SYS_futex, &value, FUTEX_WAKE_PRIVATE, 1, NULL, NULL, 0) != 0) return 7;
        errno = 0;
        if (syscall(SYS_futex, &value, FUTEX_WAIT_PRIVATE, 0, &timeout, NULL, 0) != -1 || errno != ETIMEDOUT) return 8;
    }
    FILE *result = fopen("/tmp/np-futex-result.json", "w");
    if (!result) return 9;
    fprintf(result, "{\"calls\":%ld,\"wait\":%ld,\"wake\":%ld,\"eagain\":%ld,\"timeout\":%ld,\"zero\":%ld,\"cpu\":%d}\n", 3 * count, 2 * count, count, count, count, count, sched_getcpu());
    if (fclose(result)) return 10;
    go = fopen("/tmp/np-futex-go", "r");
    if (!go || fgetc(go) != 'S') return 11;
    fclose(go);
    return 0;
}
