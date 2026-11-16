#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <inttypes.h>
#include <linux/fs.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/statfs.h>
#include <sys/statvfs.h>
#include <unistd.h>

static const char payload[] = "owned-ext4-resize-proof-v1\n";
static void fail(const char *what) { perror(what); exit(1); }
static void value(const char *path, char *result, size_t size) {
    int fd = open(path, O_RDONLY | O_NOFOLLOW);
    if (fd < 0) { snprintf(result, size, "unknown: errno %d", errno); return; }
    ssize_t n = read(fd, result, size - 1); close(fd);
    if (n < 0) { snprintf(result, size, "unknown: errno %d", errno); return; }
    result[n] = 0; result[strcspn(result, "\n")] = 0;
}
int main(int argc, char **argv) {
    if (argc != 2 || (strcmp(argv[1], "write") && strcmp(argv[1], "read") && strcmp(argv[1], "grow"))) return 2;
    int root = open("/state", O_RDONLY | O_DIRECTORY | O_NOFOLLOW);
    if (root < 0) fail("open state");
    struct statfs fs; struct statvfs before, after;
    if (fstatfs(root, &fs) || fstatvfs(root, &before)) fail("stat filesystem");
    if (fs.f_type != 0xef53) return 3;
    if (!strcmp(argv[1], "write")) {
        int fd = openat(root, "proof", O_WRONLY | O_CREAT | O_EXCL | O_NOFOLLOW, 0600);
        if (fd < 0) fail("create proof");
        if (write(fd, payload, sizeof(payload)-1) != sizeof(payload)-1 || fsync(fd) || close(fd) || fsync(root)) fail("persist proof");
    } else {
        char readback[sizeof(payload)] = {0};
        int fd = openat(root, "proof", O_RDONLY | O_NOFOLLOW);
        if (fd < 0) fail("open proof");
        ssize_t count = read(fd, readback, sizeof(readback)); close(fd);
        if (count != sizeof(payload)-1 || memcmp(readback, payload, sizeof(payload)-1)) return 4;
    }
    int disk = open("/dev/vda", O_RDONLY | O_NOFOLLOW);
    uint64_t bytes = 0;
    if (disk < 0 || ioctl(disk, BLKGETSIZE64, &bytes)) fail("device capacity");
    if (!strcmp(argv[1], "grow")) {
        if (!before.f_frsize || bytes % before.f_frsize) return 5;
        uint64_t blocks = bytes / before.f_frsize;
        /* Linux ext4 ioctl ABI: fs/ext4/ext4.h, EXT4_IOC_RESIZE_FS. */
        if (ioctl(root, _IOW('f', 16, uint64_t), &blocks)) fail("EXT4_IOC_RESIZE_FS");
        if (syncfs(root)) fail("sync filesystem");
    }
    if (fstatvfs(root, &after)) fail("stat resized filesystem");
    char cache[128], zeroes[128], discard[128];
    value("/sys/block/vda/queue/write_cache", cache, sizeof(cache));
    value("/sys/block/vda/queue/write_zeroes_max_bytes", zeroes, sizeof(zeroes));
    value("/sys/block/vda/queue/discard_max_bytes", discard, sizeof(discard));
    printf("{\"ok\":true,\"device_bytes\":%" PRIu64 ",\"statvfs_fragment_bytes\":%lu,\"statvfs_blocks_before\":%lu,\"statvfs_blocks_after\":%lu,\"write_cache\":\"%s\",\"write_zeroes_max_bytes\":\"%s\",\"discard_max_bytes\":\"%s\"}\n", bytes, before.f_frsize, before.f_blocks, after.f_blocks, cache, zeroes, discard);
    close(disk); close(root); return 0;
}
