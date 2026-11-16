#define _GNU_SOURCE
#include <errno.h>
#include <linux/futex.h>
#include <pthread.h>
#include <sched.h>
#include <stdatomic.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <sys/resource.h>
#include <sys/syscall.h>
#include <time.h>
#include <unistd.h>

_Static_assert(sizeof(atomic_int) == 4, "Linux futex requires a 32-bit word");
static atomic_int turn;
static atomic_int failed;
static pthread_barrier_t ready;
static long iterations;
struct result {
    int id, cpu, tid, first_cpu, last_cpu, migrations, affinity_ok;
    long completed, waits, wakes;
    struct rusage usage;
};

static void *worker(void *value) {
    struct result *r = value;
    r->tid = (int)syscall(SYS_gettid);
    cpu_set_t mask, actual;
    CPU_ZERO(&mask);
    CPU_SET(r->cpu, &mask);
    if (pthread_setaffinity_np(pthread_self(), sizeof(mask), &mask) ||
        pthread_getaffinity_np(pthread_self(), sizeof(actual), &actual)) {
        atomic_store(&failed, 1);
    } else {
        r->affinity_ok = CPU_COUNT(&actual) == 1 && CPU_ISSET(r->cpu, &actual);
        if (!r->affinity_ok) atomic_store(&failed, 1);
    }
    r->first_cpu = r->last_cpu = sched_getcpu();
    pthread_barrier_wait(&ready);
    if (atomic_load(&failed)) return NULL;
    for (long i = 0; i < iterations; ++i) {
        while (atomic_load_explicit(&turn, memory_order_acquire) != r->id) {
            ++r->waits;
            int rc = (int)syscall(SYS_futex, &turn, FUTEX_WAIT_PRIVATE, 1-r->id, NULL, NULL, 0);
            if (rc && errno != EAGAIN && errno != EINTR) {
                atomic_store(&failed, 1);
                return NULL;
            }
        }
        int cpu = sched_getcpu();
        if (cpu != r->last_cpu) ++r->migrations;
        r->last_cpu = cpu;
        if (cpu != r->cpu) atomic_store(&failed, 1);
        ++r->completed;
        atomic_store_explicit(&turn, 1-r->id, memory_order_release);
        ++r->wakes;
        if (syscall(SYS_futex, &turn, FUTEX_WAKE_PRIVATE, 1, NULL, NULL, 0) < 0) {
            atomic_store(&failed, 1);
            return NULL;
        }
    }
    getrusage(RUSAGE_THREAD, &r->usage);
    return NULL;
}

static long number(const char *text, long maximum) {
    char *end;
    errno = 0;
    long value = strtol(text, &end, 10);
    if (errno || *end || end == text || value < 0 || value > maximum) exit(2);
    return value;
}

int main(int argc, char **argv) {
    if (argc != 4) return 2;
    struct result results[2] = {{.id=0}, {.id=1}};
    results[0].cpu = (int)number(argv[1], CPU_SETSIZE-1);
    results[1].cpu = (int)number(argv[2], CPU_SETSIZE-1);
    iterations = number(argv[3], 1000000000);
    if (!iterations) return 2;
    alarm(30);
    if (pthread_barrier_init(&ready, NULL, 3)) return 2;
    pthread_t threads[2];
    for (int i = 0; i < 2; ++i)
        if (pthread_create(&threads[i], NULL, worker, &results[i])) return 2;
    struct timespec start, finish;
    clock_gettime(CLOCK_MONOTONIC_RAW, &start);
    pthread_barrier_wait(&ready);
    for (int i = 0; i < 2; ++i) pthread_join(threads[i], NULL);
    clock_gettime(CLOCK_MONOTONIC_RAW, &finish);
    double seconds = finish.tv_sec-start.tv_sec + (finish.tv_nsec-start.tv_nsec)/1e9;
    int ok = !atomic_load(&failed) && results[0].completed == iterations && results[1].completed == iterations && atomic_load(&turn) == 0;
    printf("{\"ok\":%s,\"clock\":\"CLOCK_MONOTONIC_RAW\",\"guest_online_cpus\":%ld,\"iterations_per_thread\":%ld,\"handoffs\":%ld,\"seconds\":%.9f,\"us_per_handoff\":%.6f,\"threads\":[", ok ? "true" : "false", sysconf(_SC_NPROCESSORS_ONLN), iterations, 2*iterations, seconds, seconds*1e6/(2*iterations));
    for (int i = 0; i < 2; ++i) {
        struct result *r = &results[i];
        printf("%s{\"tid\":%d,\"requested_cpu\":%d,\"first_cpu\":%d,\"last_cpu\":%d,\"affinity_ok\":%s,\"migrations\":%d,\"completed\":%ld,\"wait_calls\":%ld,\"wake_calls\":%ld,\"voluntary_switches\":%ld,\"involuntary_switches\":%ld}", i ? "," : "", r->tid, r->cpu, r->first_cpu, r->last_cpu, r->affinity_ok ? "true" : "false", r->migrations, r->completed, r->waits, r->wakes, r->usage.ru_nvcsw, r->usage.ru_nivcsw);
    }
    puts("]}");
    pthread_barrier_destroy(&ready);
    return ok ? 0 : 1;
}
