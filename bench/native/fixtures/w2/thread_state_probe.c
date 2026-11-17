#define _POSIX_C_SOURCE 200809L
#include <dlfcn.h>
#include <errno.h>
#include <poll.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/prctl.h>
#include <unistd.h>
typedef struct _ts PyThreadState;
static void *symbol(void *library,const char *name) {
    dlerror();
    void *address=dlsym(library,name);
    const char *error=dlerror();
    if(error||!address){fprintf(stderr,"missing symbol %s: %s\n",name,error?error:"null");exit(2);}
    return address;
}
static char marker(const char *text) {
    size_t remaining=strlen(text);
    while(remaining){ssize_t n=write(STDOUT_FILENO,text,remaining);if(n<0&&errno==EINTR)continue;if(n<=0)exit(3);text+=n;remaining-=(size_t)n;}
    struct pollfd input={.fd=STDIN_FILENO,.events=POLLIN};
    int ready;
    do{ready=poll(&input,1,30000);}while(ready<0&&errno==EINTR);
    if(ready!=1||!(input.revents&POLLIN))exit(3);
    char value;ssize_t n;
    do{n=read(STDIN_FILENO,&value,1);}while(n<0&&errno==EINTR);
    if(n!=1||(value!='G'&&value!='X'))exit(3);
    return value;
}
int main(int argc,char **argv) {
    if(argc!=3||strlen(argv[1])!=15||strncmp(argv[1],"npu",3))return 2;
    for(size_t i=3;i<15;i++)if(!strchr("0123456789abcdef",argv[1][i]))return 2;
    char *end;errno=0;unsigned long count=strtoul(argv[2],&end,10);
    if(errno||!*argv[2]||*end||count<1||count>100000)return 2;
    if(prctl(PR_SET_NAME,argv[1],0,0,0))return 2;
    void *library=dlopen("/usr/local/lib/libpython3.13.so.1.0",RTLD_NOW|RTLD_GLOBAL);
    if(!library){fprintf(stderr,"dlopen: %s\n",dlerror());return 2;}
    void (*initialize)(void)=(void (*)(void))symbol(library,"Py_Initialize");
    PyThreadState *(*save)(void)=(PyThreadState *(*)(void))symbol(library,"PyEval_SaveThread");
    void (*restore)(PyThreadState *)=(void (*)(PyThreadState *))symbol(library,"PyEval_RestoreThread");
    int (*finalize)(void)=(int (*)(void))symbol(library,"Py_FinalizeEx");
    initialize();
    char command=marker("READY\n");
    unsigned rounds=0;
    while(command=='G'&&rounds<2){
        for(unsigned long i=0;i<count;i++){PyThreadState *state=save();restore(state);}
        rounds++;command=marker("DONE\n");
    }
    if(command!='X')return 3;
    if(finalize()<0)return 4;
    if(dlclose(library))return 4;
    return 0;
}
