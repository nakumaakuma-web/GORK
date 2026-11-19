'use strict';
const $ = (id) => document.getElementById(id);
let chosen=null, type=null, objectURL=null, depth='fast', latest=null, active='positive_ru';
const groups=[
  ['positive_ru','Positive RU'], ['positive_en','Positive EN'],
  ['negative_ru','Negative RU'], ['negative_en','Negative EN'],
  ['appearance_ru','Внешность'], ['pose_ru','Поза / анатомия'],
  ['clothing_ru','Одежда'], ['style_ru','Стиль / свет'],
  ['uncertainty_ru','Неопределённости'], ['framepack_ru','FramePack RU'],
  ['framepack_en','FramePack EN'], ['timeline_ru','Хронология']
];
function status(s, danger=false){ $('statusline').textContent=s; $('statusline').style.color=danger?'#f09d99':'#d6bbdf'; }
function render(){
  $('tabs').innerHTML='';$('results').innerHTML='';
  groups.forEach(([key,label])=>{
    const tab=document.createElement('button');tab.className='tab'+(key===active?' active':'');tab.textContent=label;tab.onclick=()=>{active=key;render();};$('tabs').appendChild(tab);
    const panel=document.createElement('div');panel.className='panel'+(key===active?' active':'');
    const head=document.createElement('div');head.className='editorhead';
    const title=document.createElement('strong');title.textContent=label;
    const copy=document.createElement('button');copy.className='btn secondary';copy.textContent='Копировать';
    const editor=document.createElement('textarea');editor.className='editor big';editor.placeholder='После анализа здесь появится текст';editor.value=latest?.sections?.[key]||'';editor.oninput=()=>{if(latest)latest.sections[key]=editor.value;};
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
      status('Извлечение кадров: '+(n+1)+'/'+count+'…');
    }
    return out;
  }finally{vid.removeAttribute('src');vid.load();}
}
function download(name,body,mime){const blob=new Blob([body],{type:mime});const a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download=name;document.body.appendChild(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(a.href),2000);}
function base(){return (chosen?.name||'prompt').replace(/\.[^.]*$/,'').replace(/[^a-zA-Zа-яА-Я0-9_-]/g,'_').slice(0,60)+'_prompts';}
$('exportJson').onclick=()=>{if(latest)download(base()+'.json',JSON.stringify({...latest,source_filename:chosen?.name},null,2),'application/json;charset=utf-8');};
$('exportTxt').onclick=()=>{if(latest)download(base()+'.txt',groups.map(([key,label])=>'=== '+label+' ===\n'+(latest.sections[key]||'')).join('\n\n'),'text/plain;charset=utf-8');};
async function streamAnalysis(payload){
  const resp=await fetch('/api/analyze',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
  if(!resp.ok)throw Error('Ошибка приложения HTTP '+resp.status+': '+(await resp.text()).slice(0,400));
  const reader=resp.body.getReader(), decoder=new TextDecoder();let remain='',done=false;
  while(!done){const piece=await reader.read();done=piece.done;remain+=decoder.decode(piece.value||new Uint8Array(),{stream:!done});let idx;
    while((idx=remain.indexOf('\n'))!==-1){const line=remain.slice(0,idx);remain=remain.slice(idx+1);if(!line.trim())continue;
      const msg=JSON.parse(line);if(msg.event==='stage')status(msg.message);
      if(msg.event==='error')throw Error(msg.message);
      if(msg.event==='done'){latest=msg.data;active='positive_ru';render();$('exportTxt').disabled=false;$('exportJson').disabled=false;
        const n=latest.complete;status('Анализ завершён. Заполнено разделов: '+n+'/'+latest.total+'. Проверь детали перед генерацией.',n<9);
        if(n<8){active='positive_ru';render(); status('Модель вернула неполный результат: '+n+'/'+latest.total+'. Исходный ответ сохранён в JSON. Проверь лимиты генерации.',true);}
      }
    }
  }
}
$('run').onclick=async()=>{
  if(!chosen)return;const b=$('run');b.disabled=true;b.textContent='Анализ выполняется…';
  try{status('Подготовка исходника…');const images=type==='video'?await framesVideo():await framesImage();status('Отправка данных в локальную Qwen…');
    await streamAnalysis({kind:type,depth,target:$('target').value,images});
  }catch(err){status('Ошибка: '+err.message,true);}
  finally{b.disabled=false;b.textContent='Извлечь промпты';}
};
async function ping(){try{const r=await fetch('/health',{cache:'no-store'});const h=await r.json();$('dot').classList.toggle('ok',!!h.ready);$('modelStatus').textContent='Qwen3.5: '+h.status;}catch{$('dot').classList.remove('ok');$('modelStatus').textContent='Нет связи с локальным приложением';}}
render();ping();setInterval(ping,12000);

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
  if(!$('run').disabled && !confirm('Программа перезапустится после обновления. Убедись, что результаты анализа сохранены. Продолжить?'))return;
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
