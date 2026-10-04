/* IQ analyzer UDP service. Replaces only echo.c in AMD's lwIP template.
 * Protocol integers and records are little endian. Max UDP payload 1044 bytes.
 * Main/platform/PHY setup remains generated from the official 2026.1 template.
 */
#include <stdint.h>
#include <string.h>
#include "xil_io.h"
#include "xil_cache.h"
#include "xil_printf.h"
#include "xiltimer.h"
#include "xparameters.h"
#include "xaxidma.h"
#include "lwip/udp.h"
#include "lwip/pbuf.h"
#include "lwip/ip_addr.h"
#define BASE 0x40000000U
#define MAGIC 0x49515531U
#define PORT 5001
#define DETECTOR_VERSION 0x00010001U
#define STREAM_VERSION 0x00010003U
#define DMA_VERSION 0x00010004U
#define DMA_TIMEOUT 10000000U
#if defined(XPAR_XAXIDMA_0_BASEADDR)
#define IQ_DMA_BASEADDR XPAR_XAXIDMA_0_BASEADDR
#elif defined(XPAR_AXI_DMA_0_BASEADDR)
#define IQ_DMA_BASEADDR XPAR_AXI_DMA_0_BASEADDR
#elif defined(XPAR_AXIDMA_0_BASEADDR)
#define IQ_DMA_BASEADDR XPAR_AXIDMA_0_BASEADDR
#else
#error "AXI DMA base address is missing from xparameters.h"
#endif
static struct udp_pcb *pcb;
static XAxiDma dma;
static ip_addr_t peer;
static uint16_t peer_port;
static int have_peer;
static uint32_t stream_sequence, last_command;
static int have_last;
static uint8_t next_result_queue;
static uint8_t cached[1044];static uint16_t cached_length;
static uint32_t rx[261],tx[384];
static uint32_t upload_block[2],upload_next[2],upload_crc_state[2]={0xffffffffU,0xffffffffU};
static uint32_t dma_buffer[2][32768] __attribute__((aligned(64)));
extern void timer_callback(void);

/* The generated SDT SCU-timer interval driver is disabled in the BSP because
 * Vitis 2026.1 can assert before its instance is ready.  Poll the always-on
 * Zynq global timer from the main loop and preserve the lwIP 50 ms cadence. */
#define GLOBAL_TIMER_BASE 0xF8F00200U
#define GLOBAL_TIMER_CONTROL 0x08U
static void poll_lwip_timer(void){
    static XTime last_tick;
    static int started;
    XTime now;
    const XTime tick=(XTime)(XPAR_CPU_CORE_CLOCK_FREQ_HZ/40U);
    if(!started){
        Xil_Out32(GLOBAL_TIMER_BASE+GLOBAL_TIMER_CONTROL,0U);
        Xil_Out32(GLOBAL_TIMER_BASE+0x00U,0U);
        Xil_Out32(GLOBAL_TIMER_BASE+0x04U,0U);
        Xil_Out32(GLOBAL_TIMER_BASE+GLOBAL_TIMER_CONTROL,1U);
        XTime_GetTime(&last_tick);
        started=1;
        return;
    }
    XTime_GetTime(&now);
    if((XTime)(now-last_tick)>=tick){
        do{last_tick+=tick;}while((XTime)(now-last_tick)>=tick);
        timer_callback();
    }
}
static uint32_t rd(uint32_t o){return Xil_In32(BASE+o);}
static void wr(uint32_t o,uint32_t v){Xil_Out32(BASE+o,v);}
static uint32_t crc32_update(uint32_t crc,const uint8_t *data,unsigned length){
    while(length--){crc^=*data++;for(unsigned bit=0;bit<8;bit++)crc=(crc>>1)^(0xedb88320U&-(crc&1U));}
    return crc;
}
static uint32_t crc32_bytes(const void *data,unsigned length){return crc32_update(0xffffffffU,data,length)^0xffffffffU;}
static int dma_wait(void){
    uint32_t timeout=DMA_TIMEOUT;
    while(XAxiDma_Busy(&dma,XAXIDMA_DMA_TO_DEVICE)&&--timeout);
    if(!timeout)return -1;
    timeout=DMA_TIMEOUT;
    while((rd(0x1d4)&1U)&&--timeout);
    return timeout?0:-1;
}
static int dma_reset(void){
    uint32_t timeout=DMA_TIMEOUT;XAxiDma_Reset(&dma);
    while(!XAxiDma_ResetIsDone(&dma)&&--timeout);
    return timeout?0:-1;
}
static err_t send_bytes(const void *data,uint16_t length){
    /* The 1700-byte BSP pool keeps every protocol datagram in one DMA-aligned
     * pbuf. Heap-backed PBUF_RAM frames were corrupted intermittently under
     * sustained bidirectional GEM traffic. */
    err_t result=ERR_MEM;
    for(unsigned copy=0;copy<2;copy++){
        struct pbuf *p=pbuf_alloc(PBUF_TRANSPORT,length,PBUF_POOL);
        if(!p)continue;
        err_t e=pbuf_take(p,data,length);
        if(e==ERR_OK)e=udp_sendto_blocking(pcb,p,&peer,peer_port);
        pbuf_free(p);
        if(e==ERR_OK)return ERR_OK;
        result=e;
    }
    return result;
}
static int readable(uint32_t o){
    if(o&3)return 0;
    if(o>=0x10000&&o<0x3c000)return 1;
    switch(o){
    case 0:case 4:case 8:case 0x10:case 0x14:case 0x18:
    case 0x1c:case 0x20:case 0x24:case 0x28:case 0x2c:case 0x30:
    case 0x34:case 0x38:case 0x3c:case 0x40:case 0x44:case 0x48:case 0x4c:
    case 0x50:case 0x54:case 0x58:case 0x5c:case 0x60:case 0x68:case 0x6c:
    case 0x7c:case 0x80:case 0x110:case 0x114:case 0x118:case 0x11c:
    case 0x120:case 0x124:case 0x128:case 0x12c:case 0x130:return 1;
    case 0x90:case 0x94:case 0x98:case 0x9c:case 0xa0:case 0xa4:case 0xa8:
    case 0x134:case 0x138:case 0x140:case 0x144:case 0x148:case 0x14c:
    case 0x150:case 0x154:case 0x158:case 0x15c:case 0x160:case 0x164:
    case 0x168:case 0x16c:case 0x170:case 0x174:case 0x178:return rd(4)>=0x00010002U;
    case 0x180:case 0x184:case 0x188:case 0x18c:case 0x190:case 0x194:
    case 0x198:case 0x19c:case 0x1a0:case 0x1a4:case 0x1a8:case 0x1ac:
    case 0x1b0:case 0x1b4:case 0x1b8:return rd(4)>=STREAM_VERSION;
    case 0x1c0:case 0x1c4:case 0x1c8:case 0x1cc:case 0x1d0:case 0x1d4:
    case 0x1d8:case 0x1dc:case 0x1e0:case 0x1e4:return rd(4)>=DMA_VERSION;
    case 0x84:case 0x88:case 0x8c:return rd(4)>=DETECTOR_VERSION;
    default:return 0;
    }
}
static void receive(void *arg,struct udp_pcb *up,struct pbuf *p,const ip_addr_t *addr,u16_t port){
    (void)arg;(void)up;
    if(!p)return;
    unsigned bytes=p->tot_len;
    if(bytes<16||bytes>sizeof(rx)||bytes%4){pbuf_free(p);return;}
    pbuf_copy_partial(p,rx,bytes,0);pbuf_free(p);
    if(rx[0]!=MAGIC)return;
    if(have_peer && (!ip_addr_cmp(addr,&peer)||port!=peer_port)){
        if((rd(8)&7)!=0)return;
        have_last=0;
    }
    ip_addr_copy(peer,*addr);peer_port=port;have_peer=1;
    if(have_last&&rx[2]==last_command){send_bytes(cached,cached_length);return;}
    uint32_t type=rx[1],seq=rx[2],count=rx[3],error=0,nout=1;
    tx[0]=MAGIC;tx[1]=type|0x80000000U;tx[2]=seq;tx[4]=0;
    if(type==1){ /* read: count words, one offset word in request */
        if(bytes!=20||count<1||count>256)error=1;
        else{
            for(uint32_t i=0;i<count;i++)if(!readable(rx[4]+4*i))error=2;
            if(!error){nout=count;for(uint32_t i=0;i<count;i++)tx[4+i]=rd(rx[4]+4*i);}
        }
    }else if(type==2){ /* control: START=1, STOP=2, ABORT=4 */
        if(bytes!=20||count!=1||(rx[4]!=1&&rx[4]!=2&&rx[4]!=4))error=1;
        else if(rx[4]==1&&((rd(8)&7)!=0||(rd(8)&0x800)||rd(0x50)!=rd(0x54)||rd(0x58)!=rd(0x5c)))error=3;
        else {
            wr(0xc,rx[4]);
            if(rx[4]==1){
                /* Arm a first-window snapshot locally, before network RTT. */
                for(unsigned wait=0;wait<10000;wait++)if((rd(8)&7)==3){wr(0x78,1);break;}
            }
        }
    }else if(type==3){ /* replay load: byte offset, followed by count IQ words */
        if(count<1||count>256||bytes!=20+4*count||(rx[4]&3)||rx[4]>131072-4*count)error=1;
        else if((rd(8)&7)!=0)error=3;
        else{
            if(rd(4)>=STREAM_VERSION)wr(0x180,0);
            for(uint32_t i=0;i<count;i++)wr(0x10000+rx[4]+4*i,rx[5+i]);
        }
    }else if(type==4){ /* config: length, cyclic, window, ROI, thresholds, confirmations, max */
        if((count!=13&&count!=15)||bytes!=16+4*count)error=1;
        else if((rd(8)&7)!=0)error=3;
        else{
            uint32_t *v=&rx[4];uint64_t on=((uint64_t)v[6]<<32)|v[5],off=((uint64_t)v[8]<<32)|v[7];
            uint32_t mode=count==15?v[13]:0,gap=count==15?v[14]:32;
            int extended=rd(4)>=DETECTOR_VERSION;
            if(v[0]<8192||v[0]>32768||(v[0]&8191)||v[1]>1||v[2]>1||v[3]>v[4]||v[4]>8191||
                v[6]>15||v[8]>15||on<=off||!v[9]||v[9]>65535||!v[10]||v[10]>65535||
                v[11]<(mode?1:v[9])||v[11]>1048576||v[12]!=0||mode>1||!gap||gap>65535)error=2;
            else if(count==15&&(!extended||(mode==1&&!(rd(0x8c)&1))))error=4;
            else{
                const uint32_t offsets[]={0x1c,0x24,0x28,0x2c,0x30,0x34,0x38,0x3c,0x40,0x44,0x48,0x4c,0x20};
                for(unsigned i=0;i<13;i++)wr(offsets[i],v[i]);
                /* Legacy requests must not inherit a previous digital-zero mode. */
                if(extended){wr(0x84,mode);wr(0x88,gap);}
                wr(0x70,1);
                if(rd(4)>=STREAM_VERSION){
                    /* Legacy capture always owns bank 0 and remains usable after a streaming session. */
                    wr(0x180,0);wr(0x18c,v[0]);wr(0x194,0);wr(0x19c,0);wr(0x184,3);
                }
            }
        }
    }else if(type==5){ /* counters latch; snapshot request/release */
        if(bytes!=20||count!=1)error=1;
        else if(rx[4]==0){
            if(rd(4)>=0x00010002U && (rd(0x134)&2))error=3;
            else wr(0x100,1);
        }
        else if(rx[4]==1 && rd(0x7c)==0)wr(0x78,1);
        else if(rx[4]==2)wr(0x78,2);
        else error=3;
    }else if(type==6){ /* streaming chunk: bank, block, sample offset, packet CRC32, IQ words */
        uint32_t bank=rx[4],block=rx[5],offset=rx[6],packet_crc=rx[7];
        uint32_t words=count>=4?count-4:0;
        if(rd(4)<STREAM_VERSION)error=4;
        else if(count<5||count>257||bytes!=16+4*count||bank>1||offset>32768-words)error=1;
        else if(crc32_bytes(&rx[8],4*words)!=packet_crc)error=6;
        else{
            uint32_t status=rd(0x188);
            if(((status&(1U<<6))&&bank==(status&1U))||((status&(1U<<3))&&bank==((status>>2)&1U)))error=3;
            else{
                if(offset==0){
                    if(rd(0x1d4)&1U){error=3;goto stream_chunk_done;}
                    upload_block[bank]=block;upload_next[bank]=0;upload_crc_state[bank]=0xffffffffU;
                }
                if(upload_block[bank]!=block||upload_next[bank]!=offset)error=5;
                else{
                    memcpy(&dma_buffer[bank][offset],&rx[8],4*words);
                    upload_crc_state[bank]=crc32_update(upload_crc_state[bank],(const uint8_t *)&rx[8],4*words);
                    upload_next[bank]+=words;tx[4]=upload_next[bank];
                }
stream_chunk_done:;
            }
        }
    }else if(type==7){ /* commit: bank, block, length, full CRC32, flags(bit0 arm) */
        uint32_t bank=rx[4],block=rx[5],length=rx[6],crc=rx[7],flags=rx[8];
        if(rd(4)<STREAM_VERSION)error=4;
        else if(count!=5||bytes!=36||bank>1||flags>1||length<8192||length>32768||(length&8191))error=1;
        else if(upload_block[bank]!=block||upload_next[bank]!=length||(upload_crc_state[bank]^0xffffffffU)!=crc)error=6;
        else if(length!=rd(0x1c))error=2;
        else if(rd(4)<DMA_VERSION)error=4;
        else{
            uint32_t status;
            Xil_DCacheFlushRange((UINTPTR)dma_buffer[bank],length*4U);
            wr(0x1c4,bank);wr(0x1c8,length);wr(0x1cc,block);wr(0x1d0,crc);wr(0x1c0,5);
            if(XAxiDma_SimpleTransfer(&dma,(UINTPTR)dma_buffer[bank],length*4U,XAXIDMA_DMA_TO_DEVICE)!=XST_SUCCESS||dma_wait())error=7;
            else if((rd(0x1d4)&7U)!=2U||rd(0x1d8)!=length||rd(0x1dc)!=crc)error=6;
            if(error){dma_reset();wr(0x1c0,2);goto stream_commit_done;}
            wr(0x180,bank);wr(0x184,flags?2U:0U);status=rd(0x188);
            if(!(status&(1U<<(4+bank))))error=3;
            else if(flags&&(status&(1U<<6))&&!(status&(1U<<3))&&((status&1U)!=bank))error=3;
            else{tx[4]=status;upload_next[bank]=0;upload_crc_state[bank]=0xffffffffU;}
stream_commit_done:;
        }
    }else if(type==8){ /* streaming status plus firmware upload progress */
        if(rd(4)<STREAM_VERSION)error=4;
        else if(count!=0||bytes!=16)error=1;
        else{
            const uint32_t offsets[]={0x188,0x18c,0x190,0x194,0x198,0x19c,0x1a0,0x1a4,0x1a8,0x1ac,0x1b0,0x1b4,0x1b8};
            nout=rd(4)>=DMA_VERSION?22:17;for(unsigned i=0;i<13;i++)tx[4+i]=rd(offsets[i]);
            tx[17]=upload_block[0];tx[18]=upload_next[0];tx[19]=upload_block[1];tx[20]=upload_next[1];
            if(nout==22){
                const uint32_t dma_offsets[]={0x1d4,0x1d8,0x1dc,0x1e0,0x1e4};
                for(unsigned i=0;i<5;i++)tx[21+i]=rd(dma_offsets[i]);
            }
        }
    }else if(type==9){ /* abort pending upload and invalidate selected bank */
        uint32_t bank=rx[4];
        if(rd(4)<STREAM_VERSION)error=4;
        else if(count!=1||bytes!=20||bank>1)error=1;
        else{
            if(rd(0x1d4)&1U){dma_reset();wr(0x1c0,2);}
            wr(0x180,bank);wr(0x184,12);upload_block[bank]=0;upload_next[bank]=0;upload_crc_state[bank]=0xffffffffU;
        }
    }else error=1;
    if(error){tx[1]=0xffffffffU;tx[4]=error;nout=1;}
    tx[3]=nout;cached_length=16+4*nout;memcpy(cached,tx,cached_length);
    last_command=seq;have_last=1;send_bytes(cached,cached_length);
}
void print_app_header(void){xil_printf("\r\nIQ analyzer: UDP 5001, sample_rate=%u Hz, FFT=%u\r\n",rd(0x10),rd(0x18));}
int start_application(void){
    if(rd(0)!=0x49514131U){xil_printf("Analyzer magic mismatch\r\n");return -1;}
    XAxiDma_Config *config=XAxiDma_LookupConfig(IQ_DMA_BASEADDR);
    if(!config||XAxiDma_CfgInitialize(&dma,config)!=XST_SUCCESS||XAxiDma_HasSg(&dma)){
        xil_printf("AXI DMA initialization failed\r\n");return -1;
    }
    XAxiDma_IntrDisable(&dma,XAXIDMA_IRQ_ALL_MASK,XAXIDMA_DMA_TO_DEVICE);
    pcb=udp_new_ip_type(IPADDR_TYPE_V4);if(!pcb)return -1;
    if(udp_bind(pcb,IP_ANY_TYPE,PORT)!=ERR_OK)return -1;
    udp_recv(pcb,receive,0);return 0;
}
static void send_records(uint32_t type,uint32_t prod_off,uint32_t cons_off,uint32_t mem,unsigned words,unsigned capacity,unsigned batch){
    uint32_t producer=rd(prod_off),consumer=rd(cons_off),count=producer-consumer;
    if(!count||count>capacity)return;
    if(count>batch)count=batch;
    tx[0]=MAGIC;tx[1]=type;tx[2]=stream_sequence;tx[3]=count;
    for(unsigned r=0;r<count;r++)for(unsigned w=0;w<words;w++)
        tx[4+r*words+w]=rd(mem+((consumer+r)&(capacity-1))*words*4+w*4);
    if(send_bytes(tx,16+count*words*4)==ERR_OK){wr(cons_off,consumer+count);stream_sequence++;}
}
int transfer_data(void){
    poll_lwip_timer();
    if(!have_peer||!pcb)return 0;
    /* Submit only one Ethernet-MTU-sized datagram per poll. Frequency records
     * need three quarters of the slots to sustain one result per 8192 samples. */
    uint8_t burst_turn=((next_result_queue++&3U)==3U);
    uint8_t have_frequency=rd(0x50)!=rd(0x54);
    uint8_t have_burst=rd(0x58)!=rd(0x5c);
    if((!burst_turn&&have_frequency)||!have_burst)
        send_records(0x100,0x50,0x54,0x30000,32,256,11);
    else
        send_records(0x101,0x58,0x5c,0x38000,16,128,16);
    return 0;
}
