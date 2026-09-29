/* Standalone SD acceptance capture. META.JSON uses FatFs LFN support.
 * SD I/O happens before/after a finite capture; PL alone provides 100 MSPS.
 * Each boot creates a new directory and never formats the card.
 */
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include "xil_io.h"
#include "xil_printf.h"
#include "xil_cache.h"
#include "sleep.h"
#include "ff.h"
#define BASE 0x40000000U
static FATFS fs;
static uint32_t buffer[2048] __attribute__((aligned(64)));
static uint32_t rd(uint32_t o){return Xil_In32(BASE+o);}
static void wr(uint32_t o,uint32_t v){Xil_Out32(BASE+o,v);}
static const char *names[]={"ZERO","POS25","NEG25","BURST","QPSK4","QPSK2","SHORT512","FULLNEG"};
static int save(const char *path,const void *data,unsigned bytes){
    FIL file;UINT n;FRESULT e=f_open(&file,path,FA_WRITE|FA_CREATE_NEW);
    if(e!=FR_OK)return 100+e;
    e=f_write(&file,data,bytes,&n);FRESULT close_result=f_close(&file);
    return e==FR_OK&&n==bytes&&close_result==FR_OK?0:120+e;
}
static int save_mmio(const char *path,uint32_t offset,unsigned words){
    if(words>2048)return 140;
    for(unsigned j=0;j<words;j++)buffer[j]=rd(offset+4*j);
    return save(path,buffer,words*4);
}
static int load_vector(unsigned v,unsigned *samples){
    char path[64];snprintf(path,sizeof path,"0:/VECTORS/%s.BIN",names[v]);
    FIL file;FRESULT e=f_open(&file,path,FA_READ);if(e!=FR_OK)return 10+e;
    unsigned size=f_size(&file),offset=0;
    if(size<32768||size>131072||(size%32768)){f_close(&file);return 30;}
    while(offset<size){
        UINT n;unsigned len=size-offset;if(len>sizeof buffer)len=sizeof buffer;
        e=f_read(&file,buffer,len,&n);if(e!=FR_OK||n!=len){f_close(&file);return 31;}
        for(unsigned j=0;j<len/4;j++)wr(0x10000+offset+4*j,buffer[j]);
        for(unsigned j=0;j<len/4;j++)if(rd(0x10000+offset+4*j)!=buffer[j]){f_close(&file);return 32;}
        offset+=len;
    }
    e=f_close(&file);if(e!=FR_OK)return 33;
    *samples=size/4;return 0;
}
static int capture(const char *run,unsigned c){
    char dir[64],path[96],meta[1536];unsigned samples=0,v=c%8,mode=c/8;
    if((rd(8)&7)!=0)return 40;
    int e=load_vector(v,&samples);if(e)return e;
    wr(0x1c,samples);wr(0x20,0);wr(0x24,0);wr(0x28,mode);
    wr(0x2c,0);wr(0x30,8191);wr(0x34,1048576);wr(0x38,0);wr(0x3c,262144);wr(0x40,0);
    wr(0x44,8);wr(0x48,32);wr(0x4c,1048576);
    /* Keep this established 16-case suite in threshold mode explicitly. */
    if(rd(4)>=0x00010001U){wr(0x84,0);wr(0x88,32);}
    wr(0x70,1);wr(0x0c,1);
    unsigned poll;
    for(poll=0;poll<100000;poll++){if((rd(8)&7)==3)break;}
    if(poll==100000){wr(0xc,4);return 41;}
    wr(0x78,1);
    for(poll=0;poll<100000;poll++){if((rd(8)&7)==0)break;}
    if(poll==100000){wr(0xc,4);return 42;}
    wr(0x100,1);
    for(poll=0;poll<100000;poll++){if((rd(0x134)&3)==1)break;}
    if(poll==100000)return 47;
    uint32_t nf=rd(0x50),nb=rd(0x58),errors=rd(0x60),snap=rd(0x7c),snap_id=rd(0x80);
    if(nf>4||nb>128)return 43;
    snprintf(dir,sizeof dir,"%s/C%02u",run,c);if(f_mkdir(dir)!=FR_OK)return 44;
    snprintf(path,sizeof path,"%s/FREQ.BIN",dir);if((e=save_mmio(path,0x30000,nf*32)))return e;
    snprintf(path,sizeof path,"%s/BURST.BIN",dir);if((e=save_mmio(path,0x38000,nb*16)))return e;
    if(snap&1){snprintf(path,sizeof path,"%s/SNAP.BIN",dir);if((e=save_mmio(path,0x3a000,2048)))return e;}
    uint32_t rate=rd(0x10);
    unsigned complete=rate&&!errors&&nf==samples/8192&&rd(0x118)==samples&&rd(0x11c)==0&&rd(0x120)==nf&&
        rd(0x12c)==0&&rd(0x130)==0&&rd(0x124)>0&&rd(0x128)>0&&
        (uint64_t)rd(0x124)*1000<=(uint64_t)rate*2&&(uint64_t)rd(0x128)*1000<=(uint64_t)rate*2;
    complete=complete&&rd(0x140)==samples&&!rd(0x144)&&rd(0x148)==samples&&!rd(0x14c)&&
        rd(0x160)==samples&&!rd(0x164)&&rd(0x168)==samples&&!rd(0x16c)&&rd(0x170)==nf&&
        !rd(0x150)&&!rd(0x174)&&!rd(0x178)&&rd(0x154)>0&&rd(0x154)<4096;
    int len=snprintf(meta,sizeof meta,
        "{\n\"source\":\"Zybo SD board capture\",\"case\":%u,\"vector\":\"%s\",\"window\":\"%s\","
        "\"sample_rate_hz\":%u,\"hardware_version\":%u,\"detector_mode\":\"threshold\",\"gap_min\":32,"
        "\"hardware_capabilities\":%u,\"timestamp_clock_hz\":%u,\"fft_clock_hz\":%u,"
        "\"record_format_version\":%u,\"scan_lanes\":%u,\"build_id\":\"%08x%08x%08x%08x\","
        "\"issued_samples\":%u,\"accepted_samples\":%u,\"fft_input_samples\":%u,\"fft_output_samples\":%u,"
        "\"fft_output_windows\":%u,\"input_fifo_high_water\":%u,\"input_rejected\":%u,"
        "\"result_queue_rejected\":%u,\"input_underreads\":%u,"
        "\"input_samples\":%u,\"epoch\":%u,\"config_id\":%u,"
        "\"frequency_records\":%u,\"burst_records\":%u,\"error_status\":%u,"
        "\"hardware_max_latency_cycles\":%u,\"hardware_max_publish_latency_cycles\":%u,"
        "\"snapshot_valid\":%s,\"snapshot_window\":%u,\"capture_complete\":%s\n}\n",
        c,names[v],mode?"hann":"rect",(unsigned)rate,(unsigned)rd(4),
        (unsigned)rd(0x8c),(unsigned)rd(0xa0),(unsigned)rd(0x14),(unsigned)rd(0xa4),(unsigned)rd(0xa8),
        (unsigned)rd(0x9c),(unsigned)rd(0x98),(unsigned)rd(0x94),(unsigned)rd(0x90),
        (unsigned)rd(0x140),(unsigned)rd(0x148),(unsigned)rd(0x160),(unsigned)rd(0x168),
        (unsigned)rd(0x170),(unsigned)rd(0x154),(unsigned)rd(0x150),(unsigned)rd(0x174),(unsigned)rd(0x178),
        samples,(unsigned)rd(0x68),(unsigned)rd(0x6c),
        (unsigned)nf,(unsigned)nb,(unsigned)errors,(unsigned)rd(0x124),(unsigned)rd(0x128),
        (snap&1)?"true":"false",(unsigned)snap_id,complete?"true":"false");
    if(len<0||(unsigned)len>=sizeof meta)return 45;
    snprintf(path,sizeof path,"%s/META.JSON",dir);if((e=save(path,meta,len)))return e;
    wr(0x54,nf);wr(0x5c,nb);wr(0x78,2);
    xil_printf("Case %u %s %s: windows=%u bursts=%u errors=%08x latency=%u cycles\r\n",
        c,names[v],mode?"Hann":"rect",nf,nb,errors,rd(0x124));
    return complete?0:46;
}
int main(void){
    Xil_ICacheEnable();Xil_DCacheEnable();
    xil_printf("\r\nIQ analyzer SD acceptance capture / sample_rate=%u Hz / FFT=%u\r\n",rd(0x10),rd(0x18));
    if(rd(0)!=0x49514131U){xil_printf("FAIL: wrong PL design\r\n");return 1;}
    if((rd(4)>>16)!=1||rd(4)<0x00010002U||!(rd(0x8c)&2)){
        xil_printf("FAIL: build identity and throughput counters required\r\n");return 6;}
    FRESULT e=f_mount(&fs,"0:/",1);
    if(e!=FR_OK){xil_printf("FAIL: FAT mount=%u; use FAT32 SD\r\n",e);return 2;}
    char run[32];FILINFO info;unsigned id;
    for(id=0;id<10000;id++){
        snprintf(run,sizeof run,"0:/RUN%04u",id);e=f_stat(run,&info);
        if(e==FR_NO_FILE)break;
        if(e!=FR_OK){xil_printf("FAIL: directory lookup=%u\r\n",e);return 3;}
    }
    if(id==10000||f_mkdir(run)!=FR_OK){xil_printf("FAIL: cannot create run directory\r\n");return 4;}
    for(unsigned c=0;c<16;c++){
        int code=capture(run,c);
        if(code){xil_printf("FAIL: case=%u code=%d; keep this card for diagnosis\r\n",c,code);return 5;}
    }
    f_mount(0,"0:/",0);
    xil_printf("SD_CAPTURE_COMPLETE %s (16 cases). Files closed; power off before removing SD.\r\n",run);
    for(;;)usleep(1000000);
}
