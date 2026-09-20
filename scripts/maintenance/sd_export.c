/* Read-only SD export helper, loaded into DDR through JTAG. Only f_mount,
 * f_opendir/readdir/closedir and f_open(FA_READ)/read/close are used.
 * Never writes BOOT.BIN, vectors, directories, partitions, or raw sectors.
 */
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include "ff.h"
#include "xil_cache.h"

#define CONTROL_ADDR 0x0ff00000U
#define OUTPUT_ADDR 0x12000000U
#define LIMIT 0x01000000U
#define MAGIC 0x53444531U
#define ARCHIVE_MAGIC 0x31584453U
#define CHUNK 32768U

struct control {
    uint32_t magic,mode,run_id,status,stage,fatfs_error;
    uint32_t bytes,records,crc,index,reserved[6];
};
struct archive_header {uint32_t magic,mode,records,bytes;};
struct item_header {char path[96];uint32_t size,crc,flags,reserved;};
_Static_assert(sizeof(struct control)==64,"Mailbox layout");
_Static_assert(sizeof(struct item_header)==112,"Archive record layout");
static volatile struct control * const ctl=(void *)CONTROL_ADDR;
static uint8_t * const output=(void *)OUTPUT_ADDR;
static FATFS fs;
static FIL file;
static DIR directory;
static FILINFO info;
static uint32_t used=sizeof(struct archive_header),records;

static uint32_t crc32_bytes(const uint8_t *p,uint32_t n){
    uint32_t crc=0xffffffffU;
    while(n--){
        crc^=*p++;
        for(unsigned b=0;b<8;b++)crc=(crc>>1)^(0xedb88320U&(0U-(crc&1U)));
    }
    return ~crc;
}
static void halt(void){for(;;)__asm__ volatile("nop");}
static void fail(unsigned stage,FRESULT error){
    ctl->stage=stage;ctl->fatfs_error=error;ctl->bytes=used;ctl->records=records;
    (void)f_mount(0,"0:/",0);
    __asm__ volatile("dsb sy" ::: "memory");
    ctl->status=0x80000000U|stage;halt();
}
static struct item_header *begin_item(const char *path,uint32_t size,uint32_t flags){
    if(strlen(path)>=96||(uint64_t)used+112+size+3>LIMIT)fail(20,FR_NOT_ENOUGH_CORE);
    struct item_header *header=(void *)(output+used);
    memset(header,0,sizeof *header);
    memcpy(header->path,path,strlen(path));header->size=size;header->flags=flags;
    used+=sizeof *header;
    return header;
}
static void append_file(const char *relative,int optional){
    char path[112];snprintf(path,sizeof path,"0:/%s",relative);
    FRESULT error=f_open(&file,path,FA_READ);
    if(optional&&error==FR_NO_FILE)return;
    if(error!=FR_OK)fail(21,error);
    if(f_size(&file)>LIMIT){(void)f_close(&file);fail(22,FR_INVALID_OBJECT);}
    uint32_t size=(uint32_t)f_size(&file),offset=0;
    struct item_header *header=begin_item(relative,size,0);
    while(offset<size){
        uint32_t length=size-offset;UINT got=0;if(length>CHUNK)length=CHUNK;
        error=f_read(&file,output+used+offset,length,&got);
        if(error!=FR_OK||got!=length){(void)f_close(&file);fail(23,error==FR_OK?FR_DISK_ERR:error);}
        offset+=length;
    }
    error=f_close(&file);if(error!=FR_OK)fail(24,error);
    header->crc=crc32_bytes(output+used,size);
    used+=size;
    while(used&3)output[used++]=0;
    records++;
}
static void append_run_names(void){
    FRESULT error=f_opendir(&directory,"0:/");if(error!=FR_OK)fail(10,error);
    for(;;){
        error=f_readdir(&directory,&info);
        if(error!=FR_OK){(void)f_closedir(&directory);fail(11,error);}
        if(!info.fname[0])break;
        if((info.fattrib&AM_DIR)&&strlen(info.fname)==7&&memcmp(info.fname,"RUN",3)==0){
            unsigned digit;
            for(digit=3;digit<7;digit++)if(info.fname[digit]<'0'||info.fname[digit]>'9')break;
            if(digit==7){(void)begin_item(info.fname,0,1);records++;}
        }
    }
    error=f_closedir(&directory);if(error!=FR_OK)fail(12,error);
}
int main(void){
    Xil_DCacheDisable();Xil_ICacheDisable();
    ctl->status=1;ctl->stage=1;ctl->fatfs_error=0;ctl->bytes=0;ctl->records=0;ctl->crc=0;ctl->index=0;
    if(ctl->magic!=MAGIC||(ctl->mode!=1&&ctl->mode!=2)||ctl->run_id>=10000)fail(1,FR_INVALID_PARAMETER);
    FRESULT error=f_mount(&fs,"0:/",1);if(error!=FR_OK)fail(2,error);
    ctl->stage=3;append_run_names();
    if(ctl->mode==1){
        static const char *vectors[]={"ZERO","POS25","NEG25","BURST","QPSK4","QPSK2","SHORT512","FULLNEG"};
        for(unsigned v=0;v<8;v++){
            char path[48];ctl->index=v;snprintf(path,sizeof path,"VECTORS/%s.BIN",vectors[v]);
            append_file(path,0);
        }
    }else{
        static const char *names[]={"META.JSON","FREQ.BIN","BURST.BIN","SNAP.BIN"};
        for(unsigned c=0;c<16;c++)for(unsigned n=0;n<4;n++){
            char path[64];ctl->index=c*4+n;
            snprintf(path,sizeof path,"RUN%04lu/C%02u/%s",(unsigned long)ctl->run_id,c,names[n]);
            append_file(path,n==3);
        }
    }
    ctl->stage=4;error=f_mount(0,"0:/",0);if(error!=FR_OK)fail(4,error);
    struct archive_header *header=(void *)output;
    header->magic=ARCHIVE_MAGIC;header->mode=ctl->mode;header->records=records;header->bytes=used;
    ctl->bytes=used;ctl->records=records;ctl->crc=crc32_bytes(output,used);ctl->stage=5;
    __asm__ volatile("dsb sy" ::: "memory");ctl->status=2;halt();
    return 0;
}
