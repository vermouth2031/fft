/* RAM-only independent-clock probe. No capture, SD, or flash writes.
 * The global timer uses CPU/2, not an FPGA FCLK. Device reads bracket the
 * PL latch, allowing a measured uncertainty interval instead of assumed RTT.
 */
#include <stdint.h>
#include "xil_io.h"
#include "xil_cache.h"
#include "xparameters.h"
#define PL 0x40000000U
#define GT 0xf8f00200U
static volatile uint32_t *const box = (volatile uint32_t *)0x0ff00000U;
static uint64_t timer(void) {
    uint32_t hi, lo, again;
    do {hi=Xil_In32(GT+4);lo=Xil_In32(GT);again=Xil_In32(GT+4);} while(hi!=again);
    return ((uint64_t)hi<<32)|lo;
}
static void put64(unsigned offset,uint64_t value) {
    box[offset]=(uint32_t)value;box[offset+1]=(uint32_t)(value>>32);
}
int main(void) {
    Xil_DCacheDisable();
    box[0]=0x434c4b35U;box[1]=1;
    box[2]=XPAR_CPU_CORE_CLOCK_FREQ_HZ;
    box[3]=Xil_In32(PL+0xa0);box[4]=11;
    box[5]=Xil_In32(0xf8000100); /* ARM_PLL_CTRL */
    box[6]=Xil_In32(0xf8000120); /* ARM_CLK_CTRL */
    box[7]=Xil_In32(0xf8000170); /* FPGA0_CLK_CTRL */
    box[8]=Xil_In32(0xf8000108); /* IO_PLL_CTRL */
    for(unsigned n=0;n<4;n++)box[9+n]=Xil_In32(PL+0x90+4*n);
    Xil_Out32(GT+8,1); /* Enable, prescale=0, comparator/interrupt disabled. */
    box[13]=Xil_In32(GT+8);
    if(Xil_In32(PL)!=0x49514131U||(Xil_In32(PL+8)&7)) {
        box[1]=0x80000001U;for(;;){}
    }
    uint64_t next=timer();
    for(unsigned n=0;n<11;n++) {
        while(timer()<next){}
        uint64_t before=timer();
        Xil_Out32(PL+0x100,1);
        unsigned ready=0;
        for(unsigned spin=0;spin<100000;spin++)
            if(Xil_In32(PL+0x134)==1){ready=1;break;}
        uint64_t after=timer();
        if(!ready){box[1]=0x80000002U;for(;;){}}
        unsigned o=16+6*n;
        put64(o,before);put64(o+2,after);
        box[o+4]=Xil_In32(PL+0x110);box[o+5]=Xil_In32(PL+0x114);
        next=after+(uint64_t)XPAR_CPU_CORE_CLOCK_FREQ_HZ/20;
    }
    box[1]=2;
    for(;;){}
}
