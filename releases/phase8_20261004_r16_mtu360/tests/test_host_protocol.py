import importlib.util,struct,unittest,sys,json,tempfile,zlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'host'))
import iq_client as h

class FakeSocket:
    def __init__(self,packets):self.packets=list(packets);self.sent=[]
    def recv(self,n):return self.packets.pop(0)
    def send(self,p):self.sent.append(p)

def record(epoch=7,number=0):
    w=[0]*32;w[0]=0x46525131;w[2]=epoch;w[3]=number;w[5]=100000000
    return struct.pack('<32I',*w)

def client(packets):
    c=h.Client.__new__(h.Client);c.sock=FakeSocket(packets);c.command_sequence=100
    c.frequency=[];c.bursts=[];c.packet_sequences=[];c._seen_packets=set();c.active_epoch=7;c.malformed_packets=0
    return c

class ProtocolTests(unittest.TestCase):
    def test_socket_recovery_preserves_peer_endpoint(self):
        c=h.Client('127.0.0.1',5001)
        try:
            endpoint=c.sock.getsockname();error=OSError('Synthetic Windows adapter reset');error.winerror=10022
            c.reopen_after_link_error(error)
            self.assertEqual(c.sock.getsockname(),endpoint)
            self.assertEqual(c.sock.getpeername(),('127.0.0.1',5001))
            self.assertEqual(c.socket_reopens,1)
            with self.assertRaises(OSError):c.reopen_after_link_error(OSError('Unrelated error'))
        finally:c.close()
    def test_packet_reorder_wrap_and_loss(self):
        self.assertEqual(h.packet_loss_count([5,3,4]),0)
        self.assertEqual(h.packet_loss_count([0,0xffffffff,1,0xfffffffe]),0)
        self.assertEqual(h.packet_loss_count([0xfffffffe,1]),2)
        self.assertEqual(h.packet_loss_count([1,1,3]),1)
    def test_interleaved_stream_during_control(self):
        stream=struct.pack('<4I',h.MAGIC,0x100,41,1)+record()
        reply=struct.pack('<5I',h.MAGIC,0x80000001,101,1,0x49514131)
        c=client([stream,reply]);self.assertEqual(c.read(0), (0x49514131,))
        self.assertEqual(c.frequency,[record()]);self.assertEqual(len(c.sock.sent),1)
    def test_old_epoch_and_duplicate_packets(self):
        def packet(seq,epoch):return struct.pack('<4I',h.MAGIC,0x100,seq,1)+record(epoch)
        c=client([packet(1,6),packet(2,7),packet(2,7)])
        for _ in range(3):c.receive()
        self.assertEqual(c.packet_sequences,[2]);self.assertEqual(len(c.frequency),1)
    def test_short_and_bad_magic(self):
        for data in (b'X',struct.pack('<4I',0,0x100,1,1)+record(),struct.pack('<4I',h.MAGIC,0x100,1,1)+record()[:-1]):
            c=client([data]);self.assertIsNone(c.receive());self.assertEqual(c.malformed_packets,1)
    def test_reject_response(self):
        c=client([struct.pack('<5I',h.MAGIC,0xffffffff,101,1,3)])
        with self.assertRaisesRegex(RuntimeError,'rejected'):c.control(1)
    def test_snapshot_word_order(self):
        c=client([]);requests=[]
        def read(offset,count=1):
            if offset==0x7c:return (1,)
            if offset==0x80:return (9,)
            return tuple((i//2 if i%2==0 else 1) for i in range((offset-0x3a000)//4,(offset-0x3a000)//4+count))
        c.read=read;c.request=lambda *args:requests.append(args)
        shot=c.snapshot();self.assertEqual(shot['window_id'],9)
        self.assertEqual(shot['power'][0],2**32);self.assertEqual(shot['power'][-1],2**32+1023)
        self.assertEqual(requests,[(5,[2])])
    def test_export_origin_and_binary_roundtrip(self):
        with tempfile.TemporaryDirectory() as d:
            h.export(d,[record()],[],{'source':'Synthetic protocol unit test'})
            self.assertEqual((Path(d)/'frequency.bin').read_bytes(),record())
            self.assertEqual(json.loads((Path(d)/'capture.json').read_text())['source'],'Synthetic protocol unit test')
    def test_stream_status_decode(self):
        c=h.Client.__new__(h.Client)
        values=[0b11111010,8192,32768,10,11,0x12,0x34,7,11,0x89abcdef,1,2,4,10,4096,11,8192]
        c.request=lambda kind,payload:tuple(values)
        status=c.stream_status()
        self.assertEqual((status['active_bank'],status['host_bank'],status['pending_bank']),(0,1,0))
        self.assertTrue(status['pending_valid']);self.assertEqual(status['current_block_id'],11)
        self.assertEqual(status['last_switch_tick'],0x189abcdef)
        self.assertEqual(status['upload_next'],[4096,8192])
    def test_dma_stream_status_decode(self):
        c=h.Client.__new__(h.Client)
        values=[0]*17+[0b1010,8192,0x12345678,7,0]
        c.request=lambda kind,payload:tuple(values)
        status=c.stream_status();self.assertTrue(status['dma']['done'])
        self.assertEqual(status['dma']['target_bank'],1);self.assertEqual(status['dma']['received_samples'],8192)
        self.assertEqual(status['dma']['computed_crc32'],0x12345678);self.assertEqual(status['dma']['completed_transfers'],7)
    def test_stream_upload_chunk_crc_and_commit(self):
        c=h.Client.__new__(h.Client);requests=[]
        def request(kind,payload):
            requests.append((kind,payload))
            if kind==6:return (payload[2]+len(payload)-4,)
            if kind==7:return (0x31,)
            if kind==8:return tuple([0]*17)
            raise AssertionError(kind)
        c.request=request
        data=b''.join(struct.pack('<I',n) for n in range(8192))
        crc,status=c.upload_stream_block(data,1,23,arm=True)
        chunks=[p for kind,p in requests if kind==6]
        self.assertEqual(len(chunks),23);self.assertEqual(chunks[0][:3],[1,23,0])
        self.assertEqual(chunks[-1][2],7920)
        for chunk in chunks:
            raw=struct.pack('<'+'I'*(len(chunk)-4),*chunk[4:])
            self.assertEqual(chunk[3],zlib.crc32(raw)&0xffffffff)
            self.assertLessEqual(16+4*len(chunk),1472)
        self.assertEqual(crc,zlib.crc32(data)&0xffffffff)
        self.assertEqual(requests[-2],(7,[1,23,8192,crc,1]))

if __name__=='__main__':unittest.main()
