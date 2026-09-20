/* RAM-only maintenance: stage and verify one image, retain the old BOOT.BIN.
 * No partition, formatting, raw-sector, unlink, or unrelated-file operations.
 * Loaded through JTAG after ps7_init; never included in a boot image.
 */
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include "ff.h"
#include "xil_cache.h"
#include "xil_printf.h"

#define CONTROL_ADDR 0x0ff00000U
#define IMAGE_ADDR   0x10000000U
#define READBACK_ADDR 0x12000000U
#define IMAGE_LIMIT  0x01000000U
#define CHUNK       32768U
#define MAGIC       0x53444231U
#define WRITE_REQUEST 0x57524954U
#define FAILED      0x80000000U

/* Exactly 16 little-endian words. The host preloads words 0..4; the program
 * only changes words 5..15. Cache remains off for JTAG/DMA coherence.
 */
struct control {
    uint32_t magic, request, size, expected_crc, nonce;
    uint32_t status, stage, fatfs_error, written, read_bytes;
    uint32_t source_crc, readback_crc, first_mismatch;
    uint32_t backup_created, installed, rollback;
};
static volatile struct control * const ctl=(void *)CONTROL_ADDR;
static const uint8_t * const image=(void *)IMAGE_ADDR;
static uint8_t * const readback=(void *)READBACK_ADDR;
static FATFS fs;
static FIL file;
static char temporary[20],backup[20];
static int mounted;

static uint32_t crc32_bytes(const uint8_t *bytes,uint32_t count){
    uint32_t crc=0xffffffffU;
    for(uint32_t n=0;n<count;n++){
        crc^=bytes[n];
        for(unsigned b=0;b<8;b++)crc=(crc>>1)^(0xedb88320U & (0U-(crc&1U)));
    }
    return ~crc;
}

static void stop_forever(void){
    __asm__ volatile("dsb sy" ::: "memory");
    for(;;)__asm__ volatile("nop");
}

static void fail(unsigned stage,FRESULT error){
    ctl->stage=stage;ctl->fatfs_error=(uint32_t)error;
    if(mounted)(void)f_mount(0,"0:/",0);
    __asm__ volatile("dsb sy" ::: "memory");
    ctl->status=FAILED|stage;
    xil_printf("SD_BOOT_UPDATE_FAIL stage=%u fatfs=%u rollback=%u\r\n",
               stage,(unsigned)error,(unsigned)ctl->rollback);
    stop_forever();
}

/* Return an error without changing names. A successful read always comes
 * from a fresh file open into a separate DDR buffer and checks every byte.
 */
static FRESULT verify_file(const char *path){
    FRESULT error=f_open(&file,path,FA_READ);
    ctl->read_bytes=0;ctl->readback_crc=0;ctl->first_mismatch=0xffffffffU;
    if(error!=FR_OK)return error;
    if(f_size(&file)!=ctl->size){(void)f_close(&file);return FR_INVALID_OBJECT;}
    memset(readback,0xa5,ctl->size);
    while(ctl->read_bytes<ctl->size){
        UINT got=0;uint32_t offset=ctl->read_bytes,length=ctl->size-offset;
        if(length>CHUNK)length=CHUNK;
        error=f_read(&file,readback+offset,length,&got);
        if(error!=FR_OK||got!=length){(void)f_close(&file);return error==FR_OK?FR_DISK_ERR:error;}
        ctl->read_bytes=offset+length;
    }
    error=f_close(&file);if(error!=FR_OK)return error;
    ctl->readback_crc=crc32_bytes(readback,ctl->size);
    for(uint32_t n=0;n<ctl->size;n++)if(readback[n]!=image[n]){
        ctl->first_mismatch=n;return FR_INT_ERR;
    }
    return ctl->readback_crc==ctl->expected_crc?FR_OK:FR_INT_ERR;
}

/* Keep both files on a failed post-install verification. Move only this
 * transaction's new image back to its unique temporary name, then restore
 * the uniquely named original. Never overwrite an existing backup.
 */
static void rollback_original(void){
    FRESULT error;
    ctl->rollback=1;
    if(ctl->installed){
        error=f_rename("0:/BOOT.BIN",temporary);
        if(error!=FR_OK){ctl->rollback=0x80000001U;return;}
        ctl->installed=0;
    }
    error=f_rename(backup,"0:/BOOT.BIN");
    if(error!=FR_OK){ctl->rollback=0x80000002U;return;}
    ctl->backup_created=0;ctl->rollback=2;
}

int main(void){
    Xil_DCacheDisable();Xil_ICacheDisable();
    ctl->status=1;ctl->stage=1;ctl->fatfs_error=0;
    ctl->written=0;ctl->read_bytes=0;ctl->source_crc=0;ctl->readback_crc=0;
    ctl->first_mismatch=0xffffffffU;ctl->backup_created=0;ctl->installed=0;ctl->rollback=0;
    if(ctl->magic!=MAGIC||ctl->request!=WRITE_REQUEST||ctl->size==0||
       ctl->size>IMAGE_LIMIT||ctl->nonce>0x0fffffffU)fail(1,FR_INVALID_PARAMETER);
    ctl->source_crc=crc32_bytes(image,ctl->size);
    if(ctl->source_crc!=ctl->expected_crc)fail(2,FR_INT_ERR);
    snprintf(temporary,sizeof temporary,"0:/N%07lX.BIN",(unsigned long)ctl->nonce);
    snprintf(backup,sizeof backup,"0:/B%07lX.BIN",(unsigned long)ctl->nonce);
    xil_printf("SD_BOOT_UPDATE_START bytes=%u temp=%s backup=%s\r\n",
               (unsigned)ctl->size,temporary,backup);
    ctl->stage=3;
    FRESULT error=f_mount(&fs,"0:/",1);
    if(error!=FR_OK)fail(3,error);
    mounted=1;
    FILINFO info;
    error=f_stat("0:/BOOT.BIN",&info);
    if(error!=FR_OK)fail(4,error);
    if(info.fattrib&AM_DIR)fail(4,FR_INVALID_NAME);
    error=f_stat(temporary,&info);
    if(error!=FR_NO_FILE)fail(5,error==FR_OK?FR_EXIST:error);
    error=f_stat(backup,&info);
    if(error!=FR_NO_FILE)fail(6,error==FR_OK?FR_EXIST:error);
    ctl->stage=7;
    error=f_open(&file,temporary,FA_WRITE|FA_CREATE_NEW);
    if(error!=FR_OK)fail(7,error);
    ctl->stage=8;
    while(ctl->written<ctl->size){
        UINT count=0;uint32_t offset=ctl->written,length=ctl->size-offset;
        if(length>CHUNK)length=CHUNK;
        error=f_write(&file,image+offset,length,&count);
        if(error!=FR_OK||count!=length){(void)f_close(&file);fail(8,error==FR_OK?FR_DISK_ERR:error);}
        ctl->written=offset+length;
    }
    ctl->stage=9;
    error=f_sync(&file);
    if(error!=FR_OK){(void)f_close(&file);fail(9,error);}
    error=f_close(&file);if(error!=FR_OK)fail(10,error);
    ctl->stage=11;
    error=verify_file(temporary);if(error!=FR_OK)fail(11,error);
    ctl->stage=12;
    error=f_rename("0:/BOOT.BIN",backup);if(error!=FR_OK)fail(12,error);
    ctl->backup_created=1;
    ctl->stage=13;
    error=f_rename(temporary,"0:/BOOT.BIN");
    if(error!=FR_OK){rollback_original();fail(13,error);}
    ctl->installed=1;
    ctl->stage=14;
    error=verify_file("0:/BOOT.BIN");
    if(error!=FR_OK){rollback_original();fail(14,error);}
    ctl->stage=15;
    error=f_mount(0,"0:/",0);mounted=0;
    if(error!=FR_OK)fail(15,error);
    __asm__ volatile("dsb sy" ::: "memory");
    ctl->status=2;
    xil_printf("SD_BOOT_UPDATE_PASS bytes=%u crc=%08x backup=%s\r\n",
               (unsigned)ctl->size,(unsigned)ctl->readback_crc,backup);
    stop_forever();
    return 0;
}
