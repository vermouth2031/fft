import fs from 'node:fs/promises';
import path from 'node:path';
import {pathToFileURL,fileURLToPath} from 'node:url';
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const skill='C:/Users/LENOVO/.codex/plugins/cache/openai-primary-runtime/presentations/26.915.20218/skills/presentations';
const modules=process.env.RUNTIME_NODE_MODULES;
const {Presentation,PresentationFile}=await import(pathToFileURL(path.join(modules,'@oai/artifact-tool/dist/artifact_tool.mjs')));
const {resolvePresentationFont,applyPresentationChartFont,finalizePresentation}=await import(pathToFileURL(path.join(skill,'container_tools/artifact_tool_utils.mjs')));
const font=resolvePresentationFont({fontFamily:'Microsoft YaHei'});
const tmp=path.join(root,'build/phase4_deck');await fs.mkdir(tmp,{recursive:true});
const sourceReport='reports/phase4_final_measurements.json';
const data=JSON.parse(await fs.readFile(path.join(root,sourceReport),'utf8'));
if(data.status!=='PASS'||data.hardware.scan_lanes!==8)throw new Error('Final combined-build measurements required');
const widest=data.minimum_widest_internal_obw_hz/1e6;
const guiPath='captures/phase4_final_20260922/demo/ofdm.png';
if(process.argv.includes('--final')){
 const complete=JSON.parse(await fs.readFile(path.join(root,'reports/phase4_complete_validation.json'),'utf8'));
 if(complete.status!=='PASS'||!complete.physical_cold_boot_verified)throw new Error('Complete final acceptance required');
 data.maximum_analysis_us=Math.max(data.maximum_analysis_us,complete.maximum_analysis_us);
 data.maximum_publish_us=Math.max(data.maximum_publish_us,complete.maximum_publish_us);
}
const p=Presentation.create({slideSize:{width:1280,height:720}});
const navy='#143449',teal='#137C89',gray='#536775';
function text(slide,value,x,y,w,h,size=30,color=navy,bold=false){
 const shape=slide.shapes.add({geometry:'textbox',position:{left:x,top:y,width:w,height:h},fill:'none',line:{fill:'none',width:0}});
 shape.text=value;shape.text.style={typeface:font,fontSize:size,color,bold,autoFit:'none'};return shape;
}
function slide(title,notes){const s=p.slides.add();s.background.fill='#FFFFFF';text(s,title,64,40,1152,74,44,navy,true);s.speakerNotes.textFrame.setText(notes);return s;}
function body(s,paragraphs){paragraphs.forEach((v,i)=>text(s,v,70,156+i*126,1120,106,30));}
function table(s,values,widths){
 const t=s.tables.add({rows:values.length,columns:values[0].length,left:64,top:154,width:1152,height:values.length*64,values,columnWidths:widths});
 for(let r=0;r<values.length;r++)for(let c=0;c<values[0].length;c++){
  const cell=t.getCell(r,c);cell.fill=r===0?navy:r%2?'#F0F5F7':'#FFFFFF';
  cell.text.style={typeface:font,fontSize:25,color:r===0?'#FFFFFF':navy,bold:r===0};
 }
 return t;
}
let s=slide('100 MSPS 数字 IQ 分析器','讲稿：介绍 Zybo Z7-20 上的数字电路项目。输入是预装载后 PL 连续回放，I/Q 各 16bit。厂商 FFT 与自有测量控制 RTL 分工明确。\n来源：reports/phase4_final_measurements.json；reports/phase4_requirements.json。');
text(s,'8192 点 FFT 与完整功率谱测量',72,190,1100,90,48,teal,true);
text(s,'幅度、突发包络长度、谱峰与 99% 占用带宽',72,318,1100,74,32);
text(s,'八路谱扫描、构建身份与真板完整验证\n2026 年 9 月 22 日',72,522,1100,110,26,gray);

s=slide('赛事数值要求与当前证据','讲稿：四项数值要求在当前声明口径下达到。输入速率不代表 USB/以太网实时上传速率，位宽不代表模拟 ADC ENOB。带宽没有公布的数值最低门槛。\n来源：docs/赛题要求.md；reports/phase4_requirements.json；reports/phase4_final_measurements.json。');
table(s,[['指标','要求','当前结果','计量口径'],['I / Q 位宽','≥12 bit','各 16 bit','数字输入格式'],['输入速率','≥100 MSPS','100 MSPS','每拍一对 IQ'],['FFT 点数','≥8192','8192','完整 FFT'],['处理时间','≤2 ms',`${data.maximum_analysis_us.toFixed(2)} µs`,'PL 首 IQ 至分析结果'],['带宽','MHz，越大越好',`约 ${widest.toFixed(2)} MHz`,'指定 OFDM 内部窗最小值']],[225,210,250,467]);
text(s,'赛方补充定义尚未确认，按现有题面说明输入、频点和帧长语义',70,590,1120,76,26,gray);

s=slide('处理架构与职责','讲稿：PS 负责文件装载、控制和结果传输。PL 以源时钟采样，时域与频域并行。异步 FIFO 连接 100 MHz 与 125 MHz 时钟域，结果重新回到源域。FFT 采用 AMD IP，自有 RTL 完成窗函数、测量、结果封装和接口。\n来源：rtl/iq_peripheral.sv；rtl/analyzer_core.sv；rtl/window_fft.sv。');
table(s,[['位置','处理内容','时钟或接口'],['PS 与电脑','装载向量，配置，读回和展示','UDP / AXI4-Lite'],['PL 源域','回放、能量、幅度、包络测长','100 MHz'],['PL FFT 域','加窗、AMD FFT、全谱功率和 CDF','125 MHz'],['PL 结果域','对齐窗口、定点换算、结果缓冲','100 MHz']],[260,620,272]);
text(s,'输入 FIFO 与结果 FIFO 跨域，窗口编号、样本位置和时间戳共同检查完整性',70,548,1120,100,28,gray);

s=slide('幅度与包络长度','讲稿：幅度由原始 I/Q 计算，结果 Q16.16，以数字码值表达。threshold 模式观察 16 点滑动能量，digital-zero 用于数字零背景。robust 档要求真实存在已声明的前导静默，不能自动识别安静背景。\n来源：rtl/time_measure.sv；rtl/digital_burst_measure.sv；host/threshold_config.py。');
body(s,['幅度：每个 IQ 对的功率为 I² + Q²\n窗口峰值和 RMS 以 Q16.16 码值输出','threshold：16 点滑动能量与迟滞门限\nrobust 档由已知静默前缀估计背景','digital-zero：确认零间隔后的非零样本区间\n包络长度不包含通信协议解析']);

s=slide('谱峰、带宽中心与 99% 带宽','讲稿：先按频率升序累计完整 8192 点功率。两端各去除 0.5% 能量，得到带宽边界。谱峰是最大功率 bin。调制载频与谱峰不同，不能统一改名。离线频点研究显示带噪场景的 CDF 中心也可能失真。\n来源：rtl/spectrum_measure.sv；rtl/result_builder.sv；build/phase4_frequency_20260922_v2/study.json。');
body(s,['谱峰：完整频谱中功率最大的 bin\n等峰取频率较低的 bin','99% 带宽：0.5% 与 99.5% 累积功率边界之差\n带宽中心：这两个边界的中点','频率分辨率为 100 MHz / 8192 ≈ 12.207 kHz\n1024 点显示快照仅用于绘图，不参与带宽计算']);

s=slide('OFDM 扩展带宽验证','讲稿：设计跨度与实际 99% 占用带宽分别报告。初始三档及次级最宽档均采用 QPSK/16QAM、矩形/Hann，各有20个冻结验收seed。次级使用与初始不同的训练和验收seed，最终组合版本复测这些输入。图中取Hann内部窗最小99%带宽，单位MHz；边沿窗单列。\n来源：reports/phase4_final_measurements.json；captures/phase4_final_20260922/ofdm_finite/measurement_validation.json；captures/phase4_final_20260922/widest_finite/measurement_validation.json。');
text(s,'Hann 窗：内部窗最小 99% 占用带宽',78,128,1120,34,22,gray);
const chart=s.charts.add('bar',{position:{left:75,top:176,width:1100,height:337},categories:['85 MHz 档','90 MHz 档','95 MHz 档','98.14 MHz 档'],series:[{name:'QPSK',values:['85','90','95','98p14'].map(b=>Number((data.bandwidth[`b${b}_qpsk_hann`].min_hz/1e6).toFixed(2))),fill:teal},{name:'16QAM',values:['85','90','95','98p14'].map(b=>Number((data.bandwidth[`b${b}_qam16_hann`].min_hz/1e6).toFixed(2))),fill:'#89AFB7'}],barOptions:{direction:'column',grouping:'clustered'},hasLegend:true,xAxis:{textStyle:{fontSize:22}},yAxis:{min:0,max:100,majorUnit:20,numberFormatCode:'0" MHz"',textStyle:{fontSize:22}},legend:{textStyle:{fontSize:22}},dataLabels:{showValue:false}});
applyPresentationChartFont(chart,{fontFamily:font});
text(s,`320 组有限输入，另有 24 组频移边界用例\n最宽设计档的内部窗最小实测占用带宽为 ${widest.toFixed(6)} MHz`,72,560,1130,100,29);

s=slide('延迟与时钟',`讲稿：最坏分析 ${data.maximum_analysis_us.toFixed(2)} 微秒，发布到板内结果缓冲 ${data.maximum_publish_us.toFixed(2)} 微秒。两者均不是电脑上传到 GUI 绘图的端到端耗时。一个窗口 81.92 微秒只代表采样时长。性能声明采用同一组合版本。\n来源：reports/phase4_final_measurements.json；reports/phase4_complete_validation.json；reports/phase2_latency_validation.json。`);
text(s,`${data.maximum_analysis_us.toFixed(2)} µs`,74,156,1100,122,82,teal,true);
text(s,'正常最大 PL 分析延迟',78,287,1100,56,32);
text(s,`最大发布延迟 ${data.maximum_publish_us.toFixed(2)} µs\n输入时钟 100 MHz，FFT 时钟 125 MHz\n单个 8192 点窗口的采样时长 81.92 µs`,78,408,1100,168,32);

s=slide('仿真、真板与持续运行','讲稿：AMD 位精确模型验证全部 FFT 点，并逐条比对测量字段。原1653组和新增367组在同一组合版本复测。持续循环验证传输和计算稳定性，不增加独立随机样本。\n来源：reports/core_validation.json；reports/phase4_final_measurements.json。');
table(s,[['验证层','规模','证据内容'],['完整核心仿真','524288 个 FFT 复数点','逐点位精确比较'],['原矩阵复测','1653 组矩阵','已知 seed 的完整回归'],['OFDM 有限输入','320 + 24 组','内部与边沿窗全部核验'],['OFDM 持续回放','920 秒','14 项 10/60/300 秒测试'],['新噪声抽样','9 组真板','预先固定 seed，数值一致']],[285,310,557]);

s=slide('稳健性与已知边界','讲稿：5dB的冻结独立seed组正常496/500，组合版本复测相同输入。噪声研究采用3153个唯一块，分别对三个幅度层统计。零事件不代表真实虚警率为零，且每块复位。没有宣称通用0dB高精度测长、DC补偿或协议帧解析。\n来源：reports/phase4_final_measurements.json；build/phase4_noise_20260922/study.json；build/phase4_frequency_20260922_v2/study.json。');
body(s,['30 / 20 / 10 dB：各 500 / 500 正常匹配\n5 dB：496 / 500；0 dB：0 / 500','不重复噪声总长 1.03317504 秒\n三个幅度层各 1051 块，观察到 0 个虚警','输入需满足声明的静默前缀与背景条件\n宽带谱峰不能直接作为调制载频']);

text(s,'零事件不等于虚警率为零；各层条件性 Poisson 95% 上界约 8.98 次/秒',70,610,1120,70,24,gray);

s=slide('真板演示界面','讲稿：这是实际Tk GUI与组合版本真板采集截图。最后一条记录可能为边沿窗，其值不能代替内部窗最小带宽统计。采集完整性与数值参考核验是不同检查，外部位精确核验保存在GUI验收报告中。\n来源：captures/phase4_final_20260922/demo/ofdm.png；captures/phase4_final_20260922/demo/gui_validation.json。');
s.images.add({blob:new Uint8Array(await fs.readFile(path.join(root,guiPath))),contentType:'image/png',alt:'组合版本真实 OFDM 板卡采集 GUI',fit:'contain',position:{left:72,top:137,width:830,height:542}});
text(s,'四个预设\n\n零背景测长\n5 dB robust\n单音峰频\n宽带 OFDM',925,172,285,400,27);

s=slide('优化结果与取舍','讲稿：八路扫描缩短谱后处理，保留全部 bin。去掉由有效标志保护的数据流水寄存器复位，以缓解实测复位扇出路径，并补充扫描中复位测试。构建 ID 与计数绑定实际版本。125 MHz 输入实验仅有 0.029 ns 裕量，本轮未晋升。\n来源：reports/第四阶段完整验收报告.md；reports/第四阶段时钟可行性结论.md。');
body(s,['八路扫描：完整 8192 bin 与原测量定义\n缩短扫描段，复位中断也不会发布旧结果','构建身份与吞吐：只读 ID 和安全跨域快照\n停止排空后核对各域样本计数守恒','125 MHz 输入实验未晋升\n时序裕量低于预定门槛，正式输入维持 100 MSPS']);

s=slide('复现与答辩','讲稿：运行 python scripts/phase4_demo.py 选择预设。打开对应原始采集目录，查看 capture.json、frequency.bin 和参考验收报告。交付包的 manifest 与 ZIP SHA-256 用于核查。预计提问：为何用 AMD FFT？明确自有测量/接口 RTL 的职责；是否外部实时？当前为板内回放；为何不直接称载频？谱峰和载频物理定义不同；循环 300 秒是否独立样本？不是，另有唯一数据研究。\n来源：scripts/phase4_demo.py；reports/第四阶段完整验收报告.md；reports/phase4_complete_validation.json。');
body(s,['演示入口：python scripts/phase4_demo.py\n预设绑定 IQ 散列、窗口和检测配置','结果核查：原始记录、冻结参考与验收报告\n构建、部署和启动证据保持对应','答辩说明：数字回放输入、AMD FFT、自有测量 RTL\n适用范围和未通过条件与实测结果一起提交']);

await fs.writeFile(path.join(tmp,'authoring.json'),JSON.stringify({slides:12,font,source_report:sourceReport,build_id:data.hardware.build_id},null,2));
const candidate=path.join(tmp,'candidate.pptx');await(await PresentationFile.exportPptx(p)).save(candidate);
for(let i=0;i<p.slides.items.length;i++){
 const png=await p.export({slide:p.slides.items[i],format:'png',scale:1});
 await fs.writeFile(path.join(tmp,`slide-${i+1}.png`),new Uint8Array(await png.arrayBuffer()));
}
if(process.argv.includes('--final')){
 const out=path.join(root,'reports/答辩材料/数字IQ分析器_答辩稿.pptx');await fs.mkdir(path.dirname(out),{recursive:true});
 await finalizePresentation({workspaceDir:root,candidatePath:candidate,finalPath:out,pythonExecutable:process.env.RUNTIME_PYTHON,
 integrityValidatorPath:path.join(skill,'container_tools/inspect_presentation_package_integrity.py'),layoutValidatorPath:path.join(skill,'container_tools/inspect_presentation_layout_geometry.py'),
 explicitTotalSlideCount:12,requiredNativeTableOwnerSlides:[2,3,8],requiredNativeChartOwnerSlides:[6],
 fontPolicy:{basis:'design',families:[font]},verifyArtifactToolImport:true,materializeLiteralChartWorkbooks:true,
 layoutArgs:['--expected-slide-size-emu','12192000,6858000','--validate-heading-fit',
 '--require-native-table-slide','2','--require-native-table-slide','3','--require-native-table-slide','8'],receiptPath:path.join(tmp,'final_validation.json')});
}
console.log('DECK_DRAFT_READY',candidate);
