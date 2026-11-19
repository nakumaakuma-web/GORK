'use strict';
const $ = (id) => document.getElementById(id);
let chosen=null, type=null, objectURL=null, depth='fast', latest=null, active='positive_ru', currentJob=null;
const groups=[
  ['positive_ru','Positive RU'], ['positive_en','Positive EN'],
  ['negative_ru','Negative RU'], ['negative_en','Negative EN'],
  ['appearance_ru','Внешность'], ['anatomy_ru','Анатомия'], ['pose_ru','Поза'],
  ['clothing_ru','Одежда'], ['style_ru','Стиль / свет'],
  ['uncertainty_ru','Неопределённости'], ['visual_passport','Визуальный паспорт JSON'], ['quality_ru','Проверка качества'], ['framepack_ru','FramePack RU'],
  ['framepack_en','FramePack EN'], ['timeline_ru','Timeline RU / Хронология']
];
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
  const extract=message.match(/Извлечение кадров:\s*(\d+)\/(\d+)/i);
  if(extract)return 'Браузер извлекает кадр '+extract[1]+' из '+extract[2]+' из видео. Генерация промптов ещё не началась.';
  if(/визуальн.*сверк|проверка.*оригинал/i.test(message))return 'Qwen повторно сравнивает описание с изображением и уточняет детали.';
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
    const tab=document.createElement('button');tab.className='tab'+(key===active?' active':'');tab.textContent=label;tab.onclick=()=>{active=key;render();};$('tabs').appendChild(tab);
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
  if(objectURL)URL.revokeObjectURL(objectURL); chosen=file;type=isVideo?'video':'photo';objectURL=URL.createObjectURL(file);
  $('drop').classList.add('loaded');$('photoPreview').style.display=isImage?'block':'none';$('videoPreview').style.display=isVideo?'block':'none';
  if(isVideo){$('videoPreview').src=objectURL;$('photoPreview').removeAttribute('src');}else{$('photoPreview').src=objectURL;$('videoPreview').removeAttribute('src');}
  $('filename').textContent=file.name+' · '+(file.size/1024/1024).toFixed(2)+' МБ · '+(isVideo?'Видео':'Фото');
  $('run').disabled=false;status('Исходник выбран. Готов к анализу.');
}
$('drop').onclick=(e)=>{if(e.target.closest('video'))return;$('file').click();};$('drop').onkeydown=(e)=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();$('file').click();}};
$('drop').addEventListener('dragover',e=>{e.preventDefault();$('drop').classList.add('drag');});
$('drop').addEventListener('dragleave',()=>{$('drop').classList.remove('drag');});
$('drop').addEventListener('drop',e=>{e.preventDefault();$('drop').classList.remove('drag');getFile(e.dataTransfer.files[0]);});
$('file').onchange=(e)=>getFile(e.target.files[0]);
$('depth').querySelectorAll('button').forEach(btn=>btn.onclick=()=>{depth=btn.dataset.val;$('depth').querySelectorAll('button').forEach(x=>x.classList.toggle('active',x===btn));});
function pause(ms){return new Promise(r=>setTimeout(r,ms));}
function canvasData(source,width,height,maxDim){const scale=Math.min(1,maxDim/Math.max(width,height));const can=document.createElement('canvas');can.width=Math.round(width*scale);can.height=Math.round(height*scale);if(!can.width||!can.height)throw Error('Не удалось определить размеры изображения.');can.getContext('2d').drawImage(source,0,0,can.width,can.height);return can.toDataURL('image/jpeg',0.91);}
async function framesImage(){const im=new Image();im.src=objectURL;await im.decode();return [{time:'',data:canvasData(im,im.naturalWidth,im.naturalHeight,depth==='deep'?1800:1350)}];}
async function framesVideo(){
  const vid=document.createElement('video');vid.preload='auto';vid.muted=true;vid.playsInline=true;vid.src=objectURL;
  await new Promise((resolve,reject)=>{const timer=setTimeout(()=>reject(new Error('Не удалось прочитать видео. Проверь формат/кодек (лучше MP4 H.264).')),18000);vid.onloadedmetadata=()=>{clearTimeout(timer);resolve();};vid.onerror=()=>{clearTimeout(timer);reject(new Error('Браузер не поддерживает кодек видео. Попробуй MP4 H.264 или WebM.'));};});
  if(!Number.isFinite(vid.duration)||vid.duration<=0||!vid.videoWidth)throw Error('Не удалось определить длительность и размеры видео.');
  const count=Math.min(8,Number($('frameCount').value));const out=[];
  try{
    for(let n=0;n<count;n++){
      const sec=Math.max(0,Math.min(vid.duration-0.04,(n+0.5)*vid.duration/count));
      await new Promise((resolve,reject)=>{
        const timer=setTimeout(()=>{vid.removeEventListener('seeked',ok);reject(Error('Не удалось прочитать кадр видео.'));},14000);
        function ok(){clearTimeout(timer);resolve();}
        vid.addEventListener('seeked',ok,{once:true});vid.currentTime=sec;
      });
      await pause(40);
      out.push({time:sec.toFixed(2),data:canvasData(vid,vid.videoWidth,vid.videoHeight,depth==='deep'?1200:980)});
      status('Извлечение кадров: '+(n+1)+'/'+count+'…');stageUpdate('Извлечение кадров: '+(n+1)+'/'+count+'…');
    }
    return out;
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
    latest=obj;active='positive_ru';render();
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
        stageEnd(false);latest=msg.data;active='positive_ru';render();$('exportTxt').disabled=false;$('exportJson').disabled=false;
        videoRepairButton();
        const cachedNote=latest.cache_hit?' Из кэша без повторной генерации.':'';
        const n=latest.complete; const issues=(latest.quality_flags||[]).filter(s=>!s.startsWith('Формальные проверки')); status('Анализ завершён: '+n+'/'+latest.total+' разделов.'+cachedNote+' '+(issues.length?'Замечания: '+issues.length+'. Открой «Проверка качества».':'Сверь результат с оригиналом.'),n<latest.total||issues.length>0);
        if(n<latest.total-4){active='positive_ru';render(); status('Модель вернула неполный результат: '+n+'/'+latest.total+'. Исходный ответ сохранён в JSON. Проверь лимиты генерации.',true);}
      }
    }
  }
}
$('run').onclick=async()=>{
  if(!chosen)return;stageBegin();const b=$('run');b.disabled=true;b.textContent='Анализ выполняется…';
  currentJob=(crypto.randomUUID ? crypto.randomUUID().replace(/-/g,'') : Array.from(crypto.getRandomValues(new Uint8Array(16)), x=>x.toString(16).padStart(2,'0')).join(''));
  $('stop').disabled=false;$('partialBox').style.display='none';$('partialPreview').textContent='';$('saveDraft').disabled=true;
  try{status('Подготовка исходника…');const images=type==='video'?await framesVideo():await framesImage();status('Отправка данных в локальную Qwen…');
    await streamAnalysis({kind:type,depth,target:$('target').value,job_id:currentJob,images});
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
render();ping();setInterval(ping,12000);
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
