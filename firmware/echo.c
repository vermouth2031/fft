/* IQ analyzer UDP service. Replaces only echo.c in AMD's lwIP template.
 * Protocol integers and records are little endian. Max UDP payload 1044 bytes.
 * Main/platform/PHY setup remains generated from the official 2026.1 template.
 */
#include <stdint.h>
#include <string.h>
#include "xil_io.h"
#include "xil_printf.h"
#include "lwip/udp.h"
#include "lwip/pbuf.h"
#include "lwip/ip_addr.h"
#define BASE 0x40000000U
#define MAGIC 0x49515531U
#define PORT 5001
static struct udp_pcb *pcb;
static ip_addr_t peer;
static uint16_t peer_port;
static int have_peer;
static uint32_t stream_sequence, last_command;
static int have_last;
static uint8_t cached[1044];static uint16_t cached_length;
static uint32_t rx[261],tx[261];
static uint32_t rd(uint32_t o){return Xil_In32(BASE+o);}
static void wr(uint32_t o,uint32_t v){Xil_Out32(BASE+o,v);}
static err_t send_bytes(const void *data,uint16_t length){
    struct pbuf *p=pbuf_alloc(PBUF_TRANSPORT,length,PBUF_RAM);
    if(!p)return ERR_MEM;
    err_t e=pbuf_take(p,data,length);
    if(e==ERR_OK)e=udp_sendto(pcb,p,&peer,peer_port);
    pbuf_free(p);return e;
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
        else for(uint32_t i=0;i<count;i++)wr(0x10000+rx[4]+4*i,rx[5+i]);
    }else if(type==4){ /* config: length, cyclic, window, ROI, thresholds, confirmations, max */
        if(bytes!=68||count!=13)error=1;
        else if((rd(8)&7)!=0)error=3;
        else{
            uint32_t *v=&rx[4];uint64_t on=((uint64_t)v[6]<<32)|v[5],off=((uint64_t)v[8]<<32)|v[7];
            if(v[0]<8192||v[0]>32768||(v[0]&8191)||v[1]>1||v[2]>1||v[3]>v[4]||v[4]>8191||
                v[6]>15||v[8]>15||on<=off||!v[9]||v[9]>65535||!v[10]||v[10]>65535||
                v[11]<v[9]||v[11]>1048576||v[12]!=0)error=2;
            else{
                const uint32_t offsets[]={0x1c,0x24,0x28,0x2c,0x30,0x34,0x38,0x3c,0x40,0x44,0x48,0x4c,0x20};
                for(unsigned i=0;i<13;i++)wr(offsets[i],v[i]);
                wr(0x70,1);
            }
        }
    }else if(type==5){ /* counters latch; snapshot request/release */
        if(bytes!=20||count!=1)error=1;
        else if(rx[4]==0)wr(0x100,1);
        else if(rx[4]==1 && rd(0x7c)==0)wr(0x78,1);
        else if(rx[4]==2)wr(0x78,2);
        else error=3;
    }else error=1;
    if(error){tx[1]=0xffffffffU;tx[4]=error;nout=1;}
    tx[3]=nout;cached_length=16+4*nout;memcpy(cached,tx,cached_length);
    last_command=seq;have_last=1;send_bytes(cached,cached_length);
}
void print_app_header(void){xil_printf("\r\nIQ analyzer: UDP 5001, 100 MSPS, FFT8192\r\n");}
int start_application(void){
    if(rd(0)!=0x49514131U){xil_printf("Analyzer magic mismatch\r\n");return -1;}
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
    if(!have_peer||!pcb)return 0;
    send_records(0x100,0x50,0x54,0x30000,32,256,8);
    send_records(0x101,0x58,0x5c,0x38000,16,128,16);
    return 0;
}
