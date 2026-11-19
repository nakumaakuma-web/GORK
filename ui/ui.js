'use strict';
const $ = (id) => document.getElementById(id);
let chosen=null, type=null, objectURL=null, depth='fast', latest=null, active='positive_ru', currentJob=null;
const photoGroups=[
  ['positive_ru','Positive RU'], ['positive_en','Positive EN'],
  ['negative_ru','Negative RU'], ['negative_en','Negative EN'],
  ['appearance_ru','Внешность'], ['anatomy_ru','Анатомия'], ['pose_ru','Поза'],
  ['clothing_ru','Одежда'], ['style_ru','Стиль / свет'],
  ['uncertainty_ru','Неопределённости'], ['visual_passport','Визуальный паспорт JSON'], ['quality_ru','Проверка качества'], ['framepack_ru','FramePack RU'],
  ['framepack_en','FramePack EN'], ['timeline_ru','Timeline RU / Хронология']
];
const videoGroups=[
  ['participants_ru','Участники'],['setting_ru','Помещение / окружение'],
  ['process_ru','Процесс / действия'],['interactions_ru','Контакты / взаимодействия'],
  ['rhythm_ru','Ритм и повторы'],['camera_ru','Камера'],['evidence_ru','Доказательства по времени'],
  ['adult_context_ru','18+ · Контекст сцены'],['uncertainty_ru','Что не подтверждено'],
  ['timeline_ru','Хронология'],['framepack_ru','Motion RU'],['framepack_en','FramePack EN'],
  ['quality_ru','Проверка качества']
];
let groups=photoGroups, sourceMode='photo';
const PES_HELP = {
  "positive_ru": "Позитивный промпт на русском. Содержит детали изображения, которые нужно воспроизвести при генерации.",
  "positive_en": "Английская версия позитивного промпта для генератора изображений.",
  "negative_ru": "Русское описание артефактов и нежелательных изменений, которых нужно избегать.",
  "negative_en": "Английский негативный промпт для генератора изображения.",
  "appearance_ru": "Видимые устойчивые признаки внешности: лицо, причёска, цвет волос, кожа и уникальные детали.",
  "anatomy_ru": "Видимые пропорции тела. Невидимые детали не должны выдаваться за установленные факты.",
  "pose_ru": "Положение головы, корпуса, рук и ног в исходном изображении. Не является анализом движения.",
  "clothing_ru": "Одежда, обувь, аксессуары и их видимые материалы.",
  "style_ru": "Художественный стиль, освещение, ракурс и композиция исходного изображения.",
  "visual_passport": "Структурированные характеристики изображения в JSON для последующего использования.",
  "participants_ru": "Кто действительно присутствует в видеоролике: количество участников, узнаваемые признаки и изменения их положения. Возраст по внешности не подтверждается.",
  "setting_ru": "Что видно в окружении: помещение или локация, мебель, предметы, освещение и фон. Не добавляет невидимые элементы.",
  "process_ru": "Фактически наблюдаемая последовательность событий: что происходит сначала, как развивается процесс и чем заканчивается.",
  "interactions_ru": "Видимые взаимодействия участников между собой и с предметами; отмечает моменты изменения контакта.",
  "rhythm_ru": "Повторяемость действий, наблюдаемый темп и изменения направления. Если данных мало, точный ритм не утверждается.",
  "camera_ru": "Движение камеры, ракурс, приближение, панорама, смена плана и стабильность съёмки.",
  "evidence_ru": "Временные точки, на которых основаны наблюдения. Позволяет проверить утверждения по ролику.",
  "adult_context_ru": "В режиме 18+ уточняет наблюдаемый контекст взрослой сцены, взаимодействия и последовательность действий без выдумывания невидимых подробностей.",
  "uncertainty_ru": "Что модель не смогла достоверно установить по доступному материалу.",
  "timeline_ru": "Последовательность подтверждённых действий с временными метками. Промежутки без наблюдений остаются неопределёнными.",
  "framepack_ru": "Русская версия инструкции движения для FramePack: действие во времени, камера и ограничения сохранения внешности.",
  "framepack_en": "Английский Motion Prompt для FramePack. Описывает развитие действия, а не только статичный кадр.",
  "quality_ru": "Замечания к результату: неполные поля, расхождения и сомнительные наблюдения."
};
function getVideoMode(){return $('videoContent').value;}
function refreshSourceMode(){
  const isVideo=sourceMode==='video';
  groups=isVideo?videoGroups.filter(([k])=>k!=='adult_context_ru'||getVideoMode()==='adult'):photoGroups;
  $('videoControls').hidden=!isVideo;
  $('photoTarget').hidden=isVideo;
  $('motionDirector').hidden=!isVideo;
  $('file').accept=isVideo?'video/*,.mp4,.webm,.mov,.mkv':'image/*,.png,.jpg,.jpeg,.webp';
  $('drop').querySelector('.empty strong').textContent=isVideo?'Выбрать видео':'Выбрать изображение';
  $('videoAdultNotice').hidden=!isVideo||getVideoMode()!=='adult';
  $('modePhoto').classList.toggle('active',!isVideo);
  $('modeVideo').classList.toggle('active',isVideo);
  $('run').textContent=isVideo?'Проанализировать видео':'Извлечь промпты из изображения';
  active=groups[0][0];render();
}
function selectSourceMode(newMode){
  if(type&&type!==newMode){
    chosen=null;type=null;
    if(objectURL){URL.revokeObjectURL(objectURL);objectURL=null;}
    $('photoPreview').removeAttribute('src');$('videoPreview').removeAttribute('src');
    $('drop').classList.remove('loaded');$('filename').textContent='Файл не выбран';
    $('run').disabled=true;$('clearSource').hidden=true;$('file').value='';$('frameStrip').style.display='none';$('frameStrip').replaceChildren();
  }
  sourceMode=newMode;refreshSourceMode();
}
$('modePhoto').onclick=()=>selectSourceMode('photo');
$('modeVideo').onclick=()=>selectSourceMode('video');
$('videoContent').onchange=()=>refreshSourceMode();

function status(s, danger=false){ $('statusline').textContent=s; $('statusline').style.color=danger?'#f09d99':'#d6bbdf'; }
// PES_STATUS_V051: UI tracks stage notifications and elapsed time, not model tokens.
const stageTracker = { running:false, startedAt:0, startedStepAt:0, step:0, last:'', history:[], timer:null };
function stageDuration(seconds){
  const n=Math.max(0,Math.floor(seconds));
  return String(Math.floor(n/60)).padStart(2,'0')+':'+String(n%60).padStart(2,'0');
}
function stageTimerUpdate(){
  if(!stageTracker.running)return;
  const now=Date.now();
  $('statusElapsed').textContent='Прошло: '+stageDuration((now-stageTracker.startedAt)/1000)
    +' · текущий этап: '+stageDuration((now-stageTracker.startedStepAt)/1000);
}
function stageDescribe(message){
  const m=message.match(/Анализ кадров\s+(\d+)\s*[–-]\s*(\d+)\s+из\s+(\d+)/i);
  if(m)return 'Qwen анализирует выбранные кадры '+m[1]+'–'+m[2]+' из '+m[3]+'. Ответ появится после завершения прохода.';
  const search=message.match(/Поиск ключевых изменений:\s*(\d+)\/(\d+)/i);
  if(search)return 'Браузер сравнивает миниатюры '+search[1]+' из '+search[2]+': ищет заметные изменения цвета и композиции. Это не анализ движения моделью.';
  if(/Выбрано \d+ ключевых кадров/i.test(message))return 'Ключевые моменты выбраны по визуальным различиям; начинается подготовка кадров для Qwen.';
  const extract=message.match(/Извлечение кадров:\s*(\d+)\/(\d+)/i);
  if(extract)return 'Браузер извлекает кадр '+extract[1]+' из '+extract[2]+' из видео. Генерация промптов ещё не началась.';
  if(/визуальн.*сверк|проверка.*оригинал/i.test(message))return 'Qwen повторно сравнивает описание с изображением и уточняет детали.';
  if(/FramePack|Timeline|Хронолог/i.test(message))return 'Qwen отдельно собирает промпты движения и хронологию по сохранённым наблюдениям выбранных кадров.';
  if(/сборка.*промпт|формирование.*промпт/i.test(message))return 'Qwen собирает Positive / Negative на русском и английском.';
  if(/исправление языка|сверка перевод/i.test(message))return 'Проверяется язык и согласованность промптов RU / EN.';
  if(/подробный анализ|внешность|анатомия|поз[аыуе]|стиль|визуальный паспорт/i.test(message))return 'Qwen уточняет детали внешности, геометрии позы и сцены.';
  if(/проверка подключения/i.test(message))return 'Проверяется доступность локального сервера Qwen.';
  if(/отправка данных/i.test(message))return 'Исходные данные передаются локальному серверу 127.0.0.1:8080.';
  return 'Выполняется текущий этап. Модель возвращает результат после окончания запроса.';
}
function stageBegin(){
  stageTracker.running=true;
  stageTracker.startedAt=Date.now();stageTracker.startedStepAt=stageTracker.startedAt;
  stageTracker.step=0;stageTracker.last='';stageTracker.history=[];
  const panel=$('statusDetails');panel.classList.remove('done','error');panel.classList.add('running');
  $('statusHistory').textContent='';
  $('statusPhase').textContent='Подготовка к анализу';
  $('statusExplanation').textContent='Сначала приложение извлечёт кадры, затем отправит их локальной Qwen.';
  if(stageTracker.timer)clearInterval(stageTracker.timer);
  stageTracker.timer=setInterval(stageTimerUpdate,1000);
  stageTimerUpdate();
}
function stageUpdate(message){
  if(!stageTracker.running || !message)return;
  if(stageTracker.last===message)return;
  stageTracker.last=message;
  stageTracker.step+=1;stageTracker.startedStepAt=Date.now();
  const clock=new Date().toLocaleTimeString('ru-RU',{hour:'2-digit',minute:'2-digit',second:'2-digit'});
  stageTracker.history.push(clock+' · '+message);
  $('statusHistory').textContent=stageTracker.history.slice(-5).join('\n');
  $('statusPhase').textContent='Этап '+stageTracker.step+' · '+message;
  $('statusExplanation').textContent=stageDescribe(message);
  stageTimerUpdate();
}
function stageEnd(failed=false, cancelled=false){
  if(!stageTracker.running)return;
  stageTracker.running=false;
  if(stageTracker.timer){clearInterval(stageTracker.timer);stageTracker.timer=null;}
  const panel=$('statusDetails');panel.classList.remove('running');panel.classList.add(failed?'error':'done');
  $('statusPhase').textContent=cancelled?'Анализ остановлен':failed?'Ошибка анализа':'Анализ завершён';
  $('statusExplanation').textContent=cancelled?'Оставлены доступные промежуточные результаты.':failed?'Подробности ошибки — в строке состояния выше.':'Результаты доступны во вкладках и для экспорта.';
  $('statusElapsed').textContent='Общее время: '+stageDuration((Date.now()-stageTracker.startedAt)/1000);
}

function render(){
  $('tabs').innerHTML='';$('results').innerHTML='';
  groups.forEach(([key,label])=>{
    const tab=document.createElement('button');tab.className='tab'+(key===active?' active':'');tab.textContent=label;tab.dataset.help=PES_HELP[key]||'Описание раздела результата анализа.';tab.onclick=()=>{active=key;render();};$('tabs').appendChild(tab);
    const panel=document.createElement('div');panel.className='panel'+(key===active?' active':'');
    const head=document.createElement('div');head.className='editorhead';
    const title=document.createElement('strong');title.textContent=label;
    const copy=document.createElement('button');copy.className='btn secondary';copy.textContent='Копировать';
    const editor=document.createElement('textarea');editor.className='editor big';editor.placeholder='После анализа здесь появится текст';editor.value=key==='visual_passport' ? (latest?.visual_passport?JSON.stringify(latest.visual_passport,null,2):'') : (latest?.sections?.[key]||'');
    editor.oninput=()=>{if(!latest)return;if(key==='visual_passport'){try{latest.visual_passport=JSON.parse(editor.value);}catch{} }else{latest.sections[key]=editor.value;}};
    copy.onclick=async()=>{try{await navigator.clipboard.writeText(editor.value);copy.textContent='Скопировано';setTimeout(()=>copy.textContent='Копировать',1200);}catch{editor.select();document.execCommand('copy');}};
    head.append(title,copy);panel.append(head,editor);$('results').appendChild(panel);
  });
}
function getFile(file){
  if(!file)return;
  const isVideo=file.type.startsWith('video/') || /\.(mp4|webm|mov|mkv)$/i.test(file.name);
  const isImage=file.type.startsWith('image/') || /\.(png|jpe?g|webp)$/i.test(file.name);
  if(!isImage&&!isVideo){status('Нужен фото- или видеофайл.',true);return;}
  sourceMode=isVideo?'video':'photo';refreshSourceMode();
  if(objectURL)URL.revokeObjectURL(objectURL); chosen=file;type=isVideo?'video':'photo';objectURL=URL.createObjectURL(file);
  $('frameStrip').style.display='none';$('frameStrip').replaceChildren();
  $('drop').classList.add('loaded');$('photoPreview').style.display=isImage?'block':'none';$('videoPreview').style.display=isVideo?'block':'none';
  if(isVideo){$('videoPreview').src=objectURL;$('photoPreview').removeAttribute('src');}else{$('photoPreview').src=objectURL;$('videoPreview').removeAttribute('src');}
  $('filename').textContent=file.name+' · '+(file.size/1024/1024).toFixed(2)+' МБ · '+(isVideo?'Видео':'Фото');
  $('clearSource').hidden=false;$('run').disabled=false;status('Исходник выбран. Готов к анализу.');
}
$('drop').onclick=(e)=>{if(e.target.closest('video')||e.target.closest('#clearSource'))return;$('file').click();};$('drop').onkeydown=(e)=>{if(e.target!==$('drop'))return;if(e.key==='Enter'||e.key===' '){e.preventDefault();$('file').click();}};
$('drop').addEventListener('dragover',e=>{e.preventDefault();$('drop').classList.add('drag');});
$('drop').addEventListener('dragleave',()=>{$('drop').classList.remove('drag');});
$('drop').addEventListener('drop',e=>{e.preventDefault();$('drop').classList.remove('drag');getFile(e.dataTransfer.files[0]);});
$('file').onchange=(e)=>getFile(e.target.files[0]);
$('depth').querySelectorAll('button').forEach(btn=>btn.onclick=()=>{depth=btn.dataset.val;$('depth').querySelectorAll('button').forEach(x=>x.classList.toggle('active',x===btn));});
function pause(ms){return new Promise(r=>setTimeout(r,ms));}
function canvasData(source,width,height,maxDim){const scale=Math.min(1,maxDim/Math.max(width,height));const can=document.createElement('canvas');can.width=Math.round(width*scale);can.height=Math.round(height*scale);if(!can.width||!can.height)throw Error('Не удалось определить размеры изображения.');can.getContext('2d').drawImage(source,0,0,can.width,can.height);return can.toDataURL('image/jpeg',0.91);}
async function framesImage(){const im=new Image();im.src=objectURL;await im.decode();return [{time:'',data:canvasData(im,im.naturalWidth,im.naturalHeight,depth==='deep'?1800:1350)}];}
// Heuristic based on coarse color differences; a cut or lighting change can look like motion.
function frameFeature(source){
  const c=document.createElement('canvas');c.width=12;c.height=12;
  const ctx=c.getContext('2d',{willReadFrequently:true});ctx.drawImage(source,0,0,12,12);
  const rgba=ctx.getImageData(0,0,12,12).data, rgb=[];
  for(let k=0;k<rgba.length;k+=4)rgb.push(rgba[k],rgba[k+1],rgba[k+2]);
  return rgb;
}
function visualDifference(a,b){
  if(!a||!b||a.length!==b.length)return 0;
  let score=0;for(let i=0;i<a.length;i++)score+=Math.abs(a[i]-b[i]);
  return score/a.length;
}
function chooseMotionCandidates(candidates, wanted){
  const n=candidates.length;wanted=Math.max(2,Math.min(wanted,n));
  if(n<=wanted)return candidates.slice();
  const chosen=[candidates[0]];
  const slots=wanted-2;
  for(let slot=0;slot<slots;slot++){
    const lo=1+Math.floor(slot*(n-2)/slots);
    const hi=1+Math.floor((slot+1)*(n-2)/slots);
    const middle=(lo+hi-1)/2;
    let best=lo,bestScore=-Infinity;
    for(let i=lo;i<hi;i++){
      const before=visualDifference(candidates[i].feature,candidates[i-1].feature);
      const after=visualDifference(candidates[i].feature,candidates[i+1].feature);
      // A small centrality tie-breaker ensures reproducible coverage in static scenes.
      const score=Math.max(before,after)+(1-Math.abs(i-middle)/Math.max(1,hi-lo))*0.01;
      if(score>bestScore){bestScore=score;best=i;}
    }
    chosen.push(candidates[best]);
  }
  chosen.push(candidates[n-1]);
  return chosen;
}
function renderFrameSamples(frames){
  const grid=$('frameStrip');grid.replaceChildren();
  if(type!=='video')return;
  frames.forEach((frame,index)=>{
    const btn=document.createElement('button');btn.type='button';btn.className='frameSample';
    btn.title='Показать этот момент в видеоплеере';
    const img=document.createElement('img');img.src=frame.data;img.alt='Ключевой кадр '+(index+1);
    const label=document.createElement('span');label.textContent=frame.time+' с';
    btn.append(img,label);btn.onclick=()=>{const video=$('videoPreview');if(video)video.currentTime=Number(frame.time);};
    grid.appendChild(btn);
  });
  grid.style.display='grid';
}
async function seekFrame(vid,sec){
  if(Math.abs(vid.currentTime-sec)<0.015 && vid.readyState>=2)return;
  await new Promise((resolve,reject)=>{
    const timer=setTimeout(()=>{vid.removeEventListener('seeked',ok);reject(Error('Не удалось перейти к кадру видео.'));},15000);
    function ok(){clearTimeout(timer);resolve();}
    vid.addEventListener('seeked',ok,{once:true});vid.currentTime=sec;
  });
}
async function framesVideo(){
  const vid=document.createElement('video');vid.preload='auto';vid.muted=true;vid.playsInline=true;vid.src=objectURL;
  await new Promise((resolve,reject)=>{const timer=setTimeout(()=>reject(new Error('Не удалось открыть видео. Лучше MP4 H.264.')),18000);
    vid.onloadedmetadata=()=>{clearTimeout(timer);resolve();};vid.onerror=()=>{clearTimeout(timer);reject(Error('Браузер не поддерживает видео.'));};});
  if(!Number.isFinite(vid.duration)||vid.duration<=0||!vid.videoWidth)throw Error('Недопустимая длительность видео.');
  const detailed=$('videoDetail').value==='detailed'||getVideoMode()==='adult';
  const samples=detailed?20:12;
  const checks=detailed?96:48;
  const minTime=Math.min(0.03,vid.duration/10),maxTime=Math.max(minTime+0.001,vid.duration-Math.min(0.03,vid.duration/10));
  const at=(i,total)=>minTime+(maxTime-minTime)*i/Math.max(1,total-1);
  const candidates=[],trace=[],out=[];
  let prev=null;
  try{
    for(let i=0;i<checks;i++){
      const sec=at(i,checks);await seekFrame(vid,sec);await pause(17);
      const feature=frameFeature(vid);const diff=prev?visualDifference(feature,prev):0;
      prev=feature;trace.push({time:sec.toFixed(3),change:Number(diff.toFixed(2))});
      candidates.push({time:sec,feature});
      if(i%4===0||i===checks-1){const msg='Видеопросмотр: '+(i+1)+' из '+checks+' временных точек';status(msg);stageUpdate(msg);}
    }
    const picked=chooseMotionCandidates(candidates,samples);
    for(let n=0;n<picked.length;n++){
      await seekFrame(vid,picked[n].time);await pause(17);
      out.push({time:picked[n].time.toFixed(3),data:canvasData(vid,vid.videoWidth,vid.videoHeight,depth==='deep'?1050:800)});
      const msg='Выбор видеомоментов: '+(n+1)+'/'+picked.length;status(msg);stageUpdate(msg);
    }
    renderFrameSamples(out);
    return {images:out,trace};
  }finally{vid.removeAttribute('src');vid.load();}
}
function download(name,body,mime){const blob=new Blob([body],{type:mime});const a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download=name;document.body.appendChild(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(a.href),2000);}
function base(){return (chosen?.name||'prompt').replace(/\.[^.]*$/,'').replace(/[^a-zA-Zа-яА-Я0-9_-]/g,'_').slice(0,60)+'_prompts';}
$('saveDraft').onclick=()=>{if($('partialPreview').textContent)download(base()+'_draft.txt',$('partialPreview').textContent,'text/plain;charset=utf-8');};
$('exportJson').onclick=()=>{if(latest)download(base()+'.json',JSON.stringify({...latest,source_filename:chosen?.name},null,2),'application/json;charset=utf-8');};
function videoRepairButton(){
  const ready=!!(latest?.kind==='video' && latest?.source_analysis &&
    ['framepack_ru','framepack_en','timeline_ru'].some(k=>!latest.sections?.[k]?.trim()));
  $('repairVideo').disabled=!ready;
}
$('importJson').onclick=()=>$('importJsonFile').click();
$('importJsonFile').onchange=async(e)=>{
  const f=e.target.files[0];e.target.value='';if(!f)return;
  try{
    if(f.size>2000000)throw Error('JSON слишком большой.');
    const obj=JSON.parse(await f.text());
    if(!obj||!obj.sections||typeof obj.sections!=='object'||!['video','photo'].includes(obj.kind))throw Error('Это не результат Prompt Extractor Studio.');
    latest=obj;sourceMode=obj.kind;if(obj.video_mode==='adult')$('videoContent').value='adult';refreshSourceMode();active=groups[0][0];render();
    $('exportTxt').disabled=false;$('exportJson').disabled=false;videoRepairButton();
    status('Загружены прежние результаты. Кадры повторно анализировать не нужно.');
  }catch(err){status('Ошибка загрузки JSON: '+err.message,true);}
};
$('repairVideo').onclick=async()=>{
  if(!latest?.source_analysis||latest.kind!=='video')return;
  const button=$('repairVideo');button.disabled=true;
  stageBegin();stageUpdate('Восстановление FramePack и хронологии из готового текстового анализа…');
  status('Отдельный запрос к Qwen: восстанавливаем недостающие поля без повторного анализа видео…');
  try{
    const resp=await fetch('/api/video/repair',{
      method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({kind:'video',sections:latest.sections,
        source_analysis:latest.source_analysis,frame_times:latest.frame_times||[]})
    });
    const obj=await resp.json();if(!resp.ok)throw Error(obj.error||'HTTP '+resp.status);
    for(const k of ['framepack_ru','framepack_en','timeline_ru'])if(obj.sections[k])latest.sections[k]=obj.sections[k];
    latest.complete=Object.entries(latest.sections).filter(([k,v])=>k!=='quality_ru'&&typeof v==='string'&&v.trim()).length;
    latest.quality_flags=[...(latest.quality_flags||[]),...(obj.notices||[])];
    if(obj.missing?.length){
      status('Не удалось заполнить: '+obj.missing.join(', ')+'. Проверь отчёт качества.',true);
      stageEnd(true);
    }else{status('FramePack RU/EN и Timeline RU заполнены. Проверь по исходному видео.');stageEnd(false);}
    active='framepack_en';render();
  }catch(err){stageEnd(true);status('Ошибка восстановления: '+err.message,true);}
  finally{videoRepairButton();}
};
$('exportTxt').onclick=()=>{if(latest)download(base()+'.txt',groups.map(([key,label])=>'=== '+label+' ===\n'+(key==='visual_passport'?JSON.stringify(latest.visual_passport||{},null,2):(latest.sections[key]||''))).join('\n\n'),'text/plain;charset=utf-8');};
async function streamAnalysis(payload){
  const resp=await fetch('/api/analyze',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
  if(!resp.ok)throw Error('Ошибка приложения HTTP '+resp.status+': '+(await resp.text()).slice(0,400));
  const reader=resp.body.getReader(), decoder=new TextDecoder();let remain='',done=false;
  while(!done){const piece=await reader.read();done=piece.done;remain+=decoder.decode(piece.value||new Uint8Array(),{stream:!done});let idx;
    while((idx=remain.indexOf('\n'))!==-1){const line=remain.slice(0,idx);remain=remain.slice(idx+1);if(!line.trim())continue;
      const msg=JSON.parse(line);if(msg.event==='stage'){status(msg.message);stageUpdate(msg.message);}
      if(msg.event==='partial'){
        $('partialBox').style.display='block';
        const el=$('partialPreview');
        el.textContent += '\n=== '+msg.stage+' ===\n'+msg.text+'\n';
        el.scrollTop=el.scrollHeight;
        $('saveDraft').disabled=false;
      }
      if(msg.event==='cancelled'){stageEnd(false,true);status(msg.message||'Анализ остановлен. Промежуточные записи доступны в блоке черновиков.',true);return;}
      if(msg.event==='error')throw Error(msg.message);
      if(msg.event==='done'){
        stageEnd(false);latest=msg.data;active=groups[0][0];render();$('exportTxt').disabled=false;$('exportJson').disabled=false;
        videoRepairButton();
        const cachedNote=latest.cache_hit?' Из кэша без повторной генерации.':'';
        const n=latest.complete; const issues=(latest.quality_flags||[]).filter(s=>!s.startsWith('Формальные проверки')); status('Анализ завершён: '+n+'/'+latest.total+' разделов.'+cachedNote+' '+(issues.length?'Замечания: '+issues.length+'. Открой «Проверка качества».':'Сверь результат с оригиналом.'),n<latest.total||issues.length>0);
        if(n<latest.total-4){active=groups[0][0];render(); status('Модель вернула неполный результат: '+n+'/'+latest.total+'. Исходный ответ сохранён в JSON. Проверь лимиты генерации.',true);}
      }
    }
  }
}
$('run').onclick=async()=>{
  if(!chosen)return;
  if(type==='video'&&getVideoMode()==='adult'&&!$('videoAdultConfirm').checked){status('Для режима 18+ подтвердите совершеннолетие участников.',true);return;}
  stageBegin();const b=$('run');b.disabled=true;b.textContent='Анализ выполняется…';
  currentJob=(crypto.randomUUID ? crypto.randomUUID().replace(/-/g,'') : Array.from(crypto.getRandomValues(new Uint8Array(16)), x=>x.toString(16).padStart(2,'0')).join(''));
  $('stop').disabled=false;$('partialBox').style.display='none';$('partialPreview').textContent='';$('saveDraft').disabled=true;
  try{status('Подготовка исходника…');const video=type==='video'?await framesVideo():null;const images=video?video.images:await framesImage();status('Отправка данных в локальную Qwen…');
    await streamAnalysis({kind:type,depth,target:type==='video'?'FramePack F1 / Video analysis':$('target').value,job_id:currentJob,
      sampling_mode:type==='video'?'temporal':'uniform',video_mode:type==='video'?getVideoMode():'legacy',
      adults_confirmed:type==='video'&&getVideoMode()==='adult'&&$('videoAdultConfirm').checked,
      temporal_trace:video?video.trace:undefined,images});
  }catch(err){stageEnd(true);status('Ошибка: '+err.message,true);}
  finally{b.disabled=false;b.textContent='Извлечь промпты';$('stop').disabled=true;currentJob=null;}
};
$('stop').onclick=async()=>{
  if(!currentJob)return;
  const id=currentJob;
  $('stop').disabled=true;
  status('Остановка запрошена. Qwen завершит текущий проход, затем дальнейшие запросы прекратятся.');
  try{
    await fetch('/api/analyze/cancel',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({job_id:id})});
  }catch(err){status('Не удалось запросить остановку: '+err.message,true);}
};
async function ping(){try{const r=await fetch('/health',{cache:'no-store'});const h=await r.json();$('dot').classList.toggle('ok',!!h.ready);$('modelStatus').textContent='Qwen3.5: '+h.status;}catch{$('dot').classList.remove('ok');$('modelStatus').textContent='Нет связи с локальным приложением';}}
refreshSourceMode();ping();setInterval(ping,12000);
fetch('/api/version',{cache:'no-store'}).then(r=>r.json()).then(x=>{
  $('versionHeader').textContent='v'+x.version;
  $('studioVersion').textContent='v'+x.version;
}).catch(()=>{});

// Manual, opt-in self-update. No update is downloaded or installed on page load.
let remoteAvailable = false;
async function checkUpdate(){
  const b=$('checkUpdate');b.disabled=true;$('updateStatus').textContent='Проверка источника обновлений…';
  remoteAvailable=false;$('installUpdate').disabled=true;
  try{
    const response=await fetch('/api/update/check',{cache:'no-store'});
    const state=await response.json();
    if(state.status==='available'){
      remoteAvailable=true;$('installUpdate').disabled=false;
      $('updateStatus').textContent='Доступна версия '+state.remote+'; установленные модели и результаты сохранятся. '+(state.message||'');
    } else if(state.status==='up_to_date'){
      $('updateStatus').textContent='Установлена актуальная версия: '+state.current;
    } else {
      $('updateStatus').textContent=state.message||'Канал обновлений не настроен.';
    }
  }catch(err){$('updateStatus').textContent='Ошибка проверки: '+err.message;}
  finally{b.disabled=false;}
}
$('checkUpdate').onclick=checkUpdate;
$('installUpdate').onclick=async()=>{
  if(!remoteAvailable)return;
  if(currentJob){$('updateStatus').textContent='Дождись завершения анализа или останови его, прежде чем обновлять программу.';return;}
  if(!confirm('Программа перезапустится после обновления. Убедись, что результаты анализа сохранены. Продолжить?'))return;
  $('installUpdate').disabled=true;$('updateStatus').textContent='Скачивание, проверка SHA-256 и установка…';
  try{
    const response=await fetch('/api/update/install',{
      method:'POST',headers:{'Content-Type':'application/json'},body:'{}'
    });
    const data=await response.json();
    if(!response.ok)throw Error(data.error||'HTTP '+response.status);
    $('updateStatus').textContent='Установлена версия '+data.version+'. Приложение перезапускается…';
    setTimeout(()=>window.location.reload(),4000);
  }catch(err){$('updateStatus').textContent='Ошибка установки: '+err.message;}
};

setTimeout(checkUpdate,1200);


// PES_MOTION_DIRECTOR_V070: build shot-by-shot RU/EN motion instructions and optionally render via local FramePack F1.
let motionResult=null, motionLastDuration=5, motionRendering=false;
function motionMessage(msg,type=''){
  const el=$('motionStatus');el.textContent=msg;el.className='dirStatus'+(type?' '+type:'');
}
function motionRenderMessage(msg,type=''){
  const el=$('motionRenderStatus');el.textContent=msg;el.className='dirStatus'+(type?' '+type:'');
}
function motionBeat(start,end,action=''){
  const box=document.createElement('div');box.className='dirBeat';
  const row=document.createElement('div');row.className='dirBeatTop';
  const from=document.createElement('label');from.textContent='С';
  const input1=document.createElement('input');input1.type='number';input1.min='0';input1.step='0.1';input1.value=String(start);input1.className='beatFrom';
  const to=document.createElement('label');to.textContent='До';
  const input2=document.createElement('input');input2.type='number';input2.min='0';input2.step='0.1';input2.value=String(end);input2.className='beatTo';
  const del=document.createElement('button');del.className='btn secondary';del.textContent='Убрать';del.type='button';
  del.onclick=()=>{if(document.querySelectorAll('#motionBeats .dirBeat').length>1)box.remove();else motionMessage('Оставь хотя бы одно действие.','error');};
  from.append(input1);to.append(input2);row.append(from,to,del);
  const content=document.createElement('textarea');content.className='dirInput beatAction';content.rows=2;content.placeholder='Что конкретно меняется в движении и положении персонажа?';content.value=action;
  box.append(row,content);$('motionBeats').appendChild(box);
}
function motionBeatDefaults(duration){
  $('motionBeats').replaceChildren();const values=[0,.3,.7,1].map(x=>Number((x*duration).toFixed(1)));
  motionBeat(values[0],values[1],'');motionBeat(values[1],values[2],'');motionBeat(values[2],values[3],'');
}
motionBeatDefaults(5);
$('motionDuration').onchange=()=>{
  const duration=Number($('motionDuration').value), old=motionLastDuration||5;
  for(const row of $('motionBeats').querySelectorAll('.dirBeat')){
    for(const cls of ['beatFrom','beatTo']){
      const inp=row.querySelector('.'+cls);
      inp.value=String(Number((Math.max(0,Number(inp.value))*duration/old).toFixed(1)));
    }
  }
  motionLastDuration=duration;
};
$('motionAddBeat').onclick=()=>{
  const rows=$('motionBeats').querySelectorAll('.dirBeat');if(rows.length>=5){motionMessage('Максимум 5 этапов, чтобы промпт оставался понятным.','error');return;}
  const duration=Number($('motionDuration').value);
  const prev=Number(rows[rows.length-1].querySelector('.beatTo').value);
  if(prev>=duration){motionMessage('Чтобы добавить этап, сначала сократи предыдущие временные интервалы.','error');return;}
  motionBeat(prev,duration,'');
};
$('motionFromAnalysis').onclick=()=>{
  if(!latest?.sections){motionMessage('Сначала выполни анализ исходной фотографии или загрузи сохранённый JSON.','error');return;}
  const sc=latest.sections;
  $('motionIdentity').value=[sc.appearance_ru,sc.anatomy_ru,sc.clothing_ru].filter(Boolean).join('\n').slice(0,3500);
  $('motionScene').value=[sc.pose_ru,sc.style_ru].filter(Boolean).join('\n').slice(0,2500);
  motionMessage('Внешность, анатомия, одежда и поза перенесены из анализа. Отредактируй и опиши движения по времени.','success');
};
function motionProject(){
  const beats=[...document.querySelectorAll('#motionBeats .dirBeat')].map(row=>({
    start:Number(row.querySelector('.beatFrom').value),
    end:Number(row.querySelector('.beatTo').value),
    action:row.querySelector('.beatAction').value.trim()
  }));
  return {
    style:$('motionStyle').value,camera:$('motionCamera').value,pace:$('motionPace').value,
    duration:Number($('motionDuration').value),rating:$('motionAdult').checked?'adult':'standard',
    adults_confirmed:$('motionAdultConfirm').checked,
    identity_ru:$('motionIdentity').value,scene_ru:$('motionScene').value,
    initial_ru:'',direction_ru:$('motionDirection').value,
    manual_en:$('motionManualEn').value,beats
  };
}
function motionRefreshRenderButton(){
  $('motionRender').disabled=motionRendering||!$('motionOutputEn').value.trim()||!chosen;
}
$('motionOutputEn').addEventListener('input',motionRefreshRenderButton);
$('motionBuild').onclick=async()=>{
  const btn=$('motionBuild');btn.disabled=true;
  motionMessage('Проверка временной шкалы. '+($('motionManualEn').value.trim()?'Использую твой готовый английский текст.':'Qwen переводит и составляет последовательность движений на английском…'));
  try{
    const resp=await fetch('/api/motion/build',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(motionProject())});
    const result=await resp.json();if(!resp.ok)throw Error(result.error||'Ошибка '+resp.status);
    motionResult=result;
    $('motionOutputRu').value=result.motion_ru;
    $('motionOutputEn').value=result.motion_en;
    $('motionOutputTimeline').value=result.shotlist_ru;
    $('motionSave').disabled=false;
    motionRefreshRenderButton();
    motionMessage('Готово: Motion Prompt RU / EN и хронология. Проверь движения и стороны тела перед запуском FramePack. '+(result.manual_input?'Qwen не запускалась.':'Текст перевела локальная Qwen.'),'success');
  }catch(err){motionMessage('Ошибка сборки: '+err.message,'error');}
  finally{btn.disabled=false;}
};
$('motionCopy').onclick=async()=>{
  const text=$('motionOutputEn').value;
  if(!text.trim()){motionMessage('Сначала составь FramePack EN или введи его вручную.','error');return;}
  try{await navigator.clipboard.writeText(text);motionMessage('FramePack EN скопирован.','success');}
  catch{const el=$('motionOutputEn');el.focus();el.select();motionMessage('Выделила текст — скопируй Ctrl+C.');}
};
$('motionLoad').onclick=()=>$('motionLoadFile').click();
$('motionLoadFile').onchange=async e=>{
  const f=e.target.files[0];e.target.value='';if(!f)return;
  try{
    if(f.size>750000)throw Error('Файл проекта слишком большой.');
    const obj=JSON.parse(await f.text());
    if(obj.kind!=='motion_director'||!obj.project||!Array.isArray(obj.project.beats))throw Error('Нужен JSON проекта режиссёра анимации.');
    const p=obj.project;
    for(const [key,element] of [['style','motionStyle'],['camera','motionCamera'],['pace','motionPace'],['duration','motionDuration']]){
      if(p[key]!==undefined)$(element).value=String(p[key]);
    }
    motionLastDuration=Number($('motionDuration').value);
    $('motionIdentity').value=p.identity_ru||'';$('motionScene').value=p.scene_ru||'';
    $('motionDirection').value=p.direction_ru||'';$('motionManualEn').value=p.manual_en||'';
    $('motionAdult').checked=p.rating==='adult';$('motionAdultConfirm').checked=!!p.adults_confirmed;
    $('motionBeats').replaceChildren();
    p.beats.slice(0,5).forEach(x=>motionBeat(Number(x.start),Number(x.end),String(x.action||'')));
    if(!p.beats.length)motionBeatDefaults(motionLastDuration);
    motionResult=obj.result||null;
    $('motionOutputEn').value=motionResult?.motion_en||'';
    $('motionOutputRu').value=motionResult?.motion_ru||'';
    $('motionOutputTimeline').value=motionResult?.shotlist_ru||'';
    $('motionSave').disabled=!motionResult;
    motionRefreshRenderButton();
    motionMessage('Проект загружен. Проверь шаги и исходный кадр перед генерацией.','success');
  }catch(error){motionMessage('Не удалось открыть проект: '+error.message,'error');}
};
$('motionSave').onclick=()=>{
  const obj={version:'0.7.0',kind:'motion_director',source_filename:chosen?.name||null,
    project:motionProject(),result:motionResult};
  download('motion_director_project.json',JSON.stringify(obj,null,2),'application/json;charset=utf-8');
  motionMessage('Проект с хронологией и промптами сохранён в JSON.','success');
};
$('motionExport').onclick=()=>{
  const data='===FRAMEPACK_EN===\n'+$('motionOutputEn').value+'\n\n===MOTION_RU===\n'+$('motionOutputRu').value+'\n\n===TIMELINE_RU===\n'+$('motionOutputTimeline').value;
  download('framepack_motion_prompt.txt',data,'text/plain;charset=utf-8');
  motionMessage('TXT с промптами и хронологией сохранён.','success');
};
function motionFPUrl(){
  const url=$('motionFramepackUrl').value.trim();
  if(!/^http:\/\/(?:127\.0\.0\.1|localhost):\d{2,5}\/?$/.test(url))throw Error('Адрес должен быть локальным: http://127.0.0.1:7860');
  return url;
}
$('motionFramepackOpen').onclick=()=>{
  try{window.open(motionFPUrl(),'_blank','noopener,noreferrer');}
  catch(e){motionRenderMessage(e.message,'error');}
};
$('motionFramepackProbe').onclick=async()=>{
  const b=$('motionFramepackProbe');b.disabled=true;motionRenderMessage('Проверка локального API FramePack…');
  try{
    const resp=await fetch('/api/framepack/probe',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({url:motionFPUrl()})});
    const info=await resp.json();if(!resp.ok)throw Error(info.error||'Ошибка '+resp.status);
    motionRenderMessage('FramePack подключён: '+info.url+' · API '+info.api+'. Можно отправлять изображение и Motion Prompt.','success');
  }catch(err){motionRenderMessage('Нет подключения: '+err.message,'error');}
  finally{b.disabled=false;}
};
async function motionStartingImage(){
  if(!chosen)throw Error('Выбери исходное изображение.');
  if(type==='photo'){const frames=await framesImage();return frames[0].data;}
  if(type==='video'){
    const v=$('videoPreview');
    if(!v||v.readyState<2||!v.videoWidth)throw Error('Открой видео в плеере и выбери кадр, который станет начальным изображением.');
    return canvasData(v,v.videoWidth,v.videoHeight,1200);
  }
  throw Error('Нет подходящего исходного кадра.');
}
async function motionStreamRender(payload){
  const resp=await fetch('/api/framepack/generate',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
  if(!resp.ok){let msg;try{msg=(await resp.json()).error;}catch{msg='HTTP '+resp.status;}throw Error(msg);}
  const reader=resp.body.getReader(),decoder=new TextDecoder();let remains='',completed=false;
  while(true){const {value,done}=await reader.read();remains+=decoder.decode(value||new Uint8Array(),{stream:!done});let idx;
    while((idx=remains.indexOf('\n'))>=0){const line=remains.slice(0,idx).trim();remains=remains.slice(idx+1);if(!line)continue;
      const event=JSON.parse(line);
      if(event.event==='stage')motionRenderMessage(event.message);
      if(event.event==='error')throw Error(event.message);
      if(event.event==='done'){
        completed=true;const v=$('motionRenderedVideo');v.src=event.video_url;v.style.display='block';
        const a=$('motionRenderedDownload');a.href=event.video_url;a.download=event.filename||'framepack.mp4';a.style.display='inline-block';
        motionRenderMessage('Готово. FramePack вернул MP4, видео сохранено локально в папке outputs приложения.','success');
      }
    }
    if(done)break;
  }
  if(!completed)throw Error('Поток FramePack завершился без подтверждения готового видео.');
}
$('motionRender').onclick=async()=>{
  if(motionRendering)return;
  try{
    const prompt=$('motionOutputEn').value.trim();if(prompt.length<10)throw Error('Составь FramePack EN перед запуском.');
    if($('motionAdult').checked&&!$('motionAdultConfirm').checked)throw Error('Для категории 18+ требуется подтвердить совершеннолетие персонажей.');
    if(!confirm('Запустить локальный FramePack? Генерация может занять много времени и использовать всю доступную VRAM. Если не хватает памяти, сначала останови Qwen.'))return;
    const image=await motionStartingImage();
    motionRendering=true;motionRefreshRenderButton();
    $('motionRenderedVideo').style.display='none';$('motionRenderedDownload').style.display='none';
    motionRenderMessage('Исходный кадр подготовлен. Проверка FramePack…');
    await motionStreamRender({url:motionFPUrl(),prompt,image,duration:Number($('motionDuration').value),
      seed:Number($('motionSeed').value),teacache:$('motionTeaCache').checked});
  }catch(err){motionRenderMessage('Ошибка генерации: '+err.message,'error');}
  finally{motionRendering=false;motionRefreshRenderButton();}
};


// PES_UI_HELP_V081 — tooltip near cursor/focus, plus removable uploaded source.
$('clearSource').addEventListener('click',(event)=>{
  event.preventDefault();event.stopPropagation();
  if(currentJob){status('Дождись завершения анализа или нажми «Остановить», затем убери файл.',true);return;}
  if(!chosen)return;
  const video=$('videoPreview');video.pause();video.removeAttribute('src');video.load();
  $('photoPreview').removeAttribute('src');
  if(objectURL)URL.revokeObjectURL(objectURL);
  objectURL=null;chosen=null;type=null;$('file').value='';
  $('drop').classList.remove('loaded');$('clearSource').hidden=true;
  $('photoPreview').style.display='none';video.style.display='none';
  $('filename').textContent='Файл не выбран';$('run').disabled=true;
  $('frameStrip').replaceChildren();$('frameStrip').style.display='none';
  status('Файл убран из окна. Сохранённые результаты и исходник на диске не затронуты.');
});
const PES_FIELD_HELP = {
  modePhoto:'В этом режиме программа анализирует одно изображение и формирует отдельные позитивные и негативные промпты.',
  modeVideo:'В этом режиме программа анализирует изменения во времени, участников, действия и готовит Motion Prompt для FramePack.',
  videoContent:'Обычное видео или 18+. Выбор 18+ усиливает внимание к последовательности взаимодействий взрослых участников.',
  videoAdultConfirm:'Подтверждение совершеннолетия всех участников обязательно для режима 18+. По внешности возраст достоверно не определяется.',
  videoDetail:'Количество временных наблюдений. Подробный режим использует больше точек, но работает дольше.',
  target:'Выбор генератора, под который будет подготовлен промпт изображения.',
  sourceModes:'Переключатель между независимыми режимами изображения и видео.',
  depth:'Глубина анализа Qwen: быстрый режим экономит время, максимальный выполняет дополнительные проверки.',
  run:'Запускает анализ выбранного файла локальной Qwen. Во время обработки результаты появляются по этапам.',
  stop:'Запрашивает остановку анализа после текущего ответа Qwen. Уже полученный черновик можно сохранить.',
  importJson:'Загрузить сохранённый JSON с результатом анализа без повторного просмотра видео.',
  exportJson:'Сохранить все разделы, временные наблюдения и служебные данные результата в JSON.',
  exportTxt:'Сохранить текстовые промпты и описания в TXT.',
  repairVideo:'Повторно запросить только недостающие Motion Prompt и хронологию, используя готовый анализ.',
  motionDirector:'Режиссёр анимации: задаёт движения по времени и превращает указания в Motion Prompt для FramePack.',
  motionStyle:'Аниме, 2.5D или фотореализм. Выбранный стиль определяет требования к неизменности внешности.',
  motionDuration:'Продолжительность планируемой анимации. Этапы движения задаются внутри этого интервала.',
  motionCamera:'Как движется виртуальная камера: неподвижно, приближение, панорама или сопровождение.',
  motionPace:'Скорость и характер движения персонажа.',
  motionIdentity:'Устойчивые признаки персонажа, которые необходимо сохранять во всех кадрах.',
  motionScene:'Где находится персонаж и с какого положения начинается движение.',
  motionDirection:'Дополнительные указания режиссёра: порядок действий, плавность, ограничения.',
  motionAddBeat:'Добавить очередной временной этап действия, не превышая длину сцены.',
  motionAdult:'Дополнительные настройки сцены только с совершеннолетними персонажами.',
  motionAdultConfirm:'Подтверждение, что все участники сцены совершеннолетние.',
  motionFromAnalysis:'Перенести внешность и исходную сцену из уже готового анализа.',
  checkUpdate:'Проверить доступную версию в GitHub. Проверка не устанавливает обновление.',
  installUpdate:'Установить доступное обновление с резервной копией. Не нажимай во время анализа.'
};
for(const [id,help] of Object.entries(PES_FIELD_HELP)){
  const node=$(id);if(!node)continue;
  node.dataset.help=help;
  const label=node.closest('.dirLabel,.field,.dirCheck');
  if(label&&!label.dataset.help)label.dataset.help=help;
}
const pesTooltip=$('pesTooltip');let pesOwner=null,pesTipDelay=null,pesVisible=false;
function pesHideHelp(){clearTimeout(pesTipDelay);pesTipDelay=null;pesOwner=null;pesVisible=false;pesTooltip.hidden=true;}
function pesMoveHelp(x,y){
  if(!pesVisible)return;
  const box=pesTooltip.getBoundingClientRect();
  let left=x+17,top=y+17;
  if(left+box.width>innerWidth-8)left=x-box.width-17;
  if(top+box.height>innerHeight-8)top=y-box.height-17;
  pesTooltip.style.left=Math.max(8,left)+'px';
  pesTooltip.style.top=Math.max(8,top)+'px';
}
function pesShowHelp(el,x,y,delay=300){
  if(!el||!el.dataset.help)return;
  if(el===pesOwner)return;
  pesHideHelp();pesOwner=el;
  pesTipDelay=setTimeout(()=>{
    if(pesOwner!==el||!document.contains(el))return;
    pesTooltip.textContent=el.dataset.help;
    pesTooltip.hidden=false;pesVisible=true;pesMoveHelp(x,y);
  },delay);
}
if(matchMedia('(hover: hover)').matches){
  document.addEventListener('pointerover',e=>{
    const el=e.target.closest?.('[data-help]');
    if(el)pesShowHelp(el,e.clientX,e.clientY);
  });
  document.addEventListener('pointermove',e=>{if(pesOwner)pesMoveHelp(e.clientX,e.clientY)});
  document.addEventListener('pointerout',e=>{
    if(pesOwner&&!pesOwner.contains(e.relatedTarget))pesHideHelp();
  });
}
document.addEventListener('focusin',e=>{
  const el=e.target.closest?.('[data-help]');
  if(!el)return;
  const r=el.getBoundingClientRect();pesShowHelp(el,r.left+r.width/2,r.bottom,150);
});
document.addEventListener('focusout',pesHideHelp);
document.addEventListener('keydown',e=>{if(e.key==='Escape')pesHideHelp();});
window.addEventListener('scroll',pesHideHelp,true);
