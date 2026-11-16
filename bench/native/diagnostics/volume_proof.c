#define _GNU_SOURCE
#include <fcntl.h>
#include <stdio.h>
#include <string.h>
#include <sys/vfs.h>
#include <unistd.h>

int main(int argc, char **argv) {
    const char value[] = "owned-volume-proof\n";
    if (argc != 2) return 2;
    int writing = strcmp(argv[1], "write") == 0;
    if (!writing && strcmp(argv[1], "read") != 0) return 2;
    int fd = open("/state/proof", writing ? O_WRONLY|O_CREAT|O_EXCL|O_NOFOLLOW : O_RDONLY|O_NOFOLLOW, 0600);
    if (fd < 0) { perror("open proof"); return 3; }
    struct statfs fs;
    if (fstatfs(fd, &fs)) { perror("statfs"); close(fd); return 4; }
    if (writing) {
        if (write(fd, value, sizeof(value)-1) != sizeof(value)-1 || fsync(fd)) {
            perror("write/fsync proof"); close(fd); return 5;
        }
        int directory = open("/state", O_RDONLY|O_DIRECTORY);
        if (directory < 0 || fsync(directory)) { perror("fsync directory"); close(fd); if (directory >= 0) close(directory); return 6; }
        close(directory);
    } else {
        char got[64];
        ssize_t count = read(fd, got, sizeof(got));
        if (count != sizeof(value)-1 || memcmp(got, value, sizeof(value)-1)) {
            fprintf(stderr, "exact volume bytes differ\n"); close(fd); return 7;
        }
    }
    close(fd);
    printf("{\"ok\":true,\"mode\":\"%s\",\"filesystem_magic\":\"%lx\"}\n", argv[1], (unsigned long)fs.f_type);
    return 0;
}
