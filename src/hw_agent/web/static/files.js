let directoryRoot=null,directoryPath='',directoryOffset=0,directoryVersion=0;
function fileTreeNode(root,path,label){
  const row=el('div',undefined,'file-tree-node'),line=el('div',undefined,'file-tree-line'),children=el('div',undefined,'file-tree-children');children.hidden=true;
  const expand=button('▸',async()=>{children.hidden=!children.hidden;expand.textContent=children.hidden?'▸':'▾';expand.setAttribute('aria-expanded',String(!children.hidden));if(!children.hidden){children.replaceChildren(el('small','불러오는 중…'));try{let offset=0;children.replaceChildren();let result;do{result=await api('/library/entries?'+new URLSearchParams({root:root.id,path,folders_only:true,offset}));result.items.forEach(f=>children.append(fileTreeNode(root,f.path,f.name)));offset+=result.items.length;}while(offset<result.total);if(!result.total)children.append(el('small','하위 폴더 없음','muted'));}catch(error){children.replaceChildren(el('small',error.message,'muted'));}}},'ghost tree-expand');
  expand.setAttribute('aria-label',label+' 하위 폴더');expand.setAttribute('aria-expanded','false');
  const open=button(label,()=>openDirectory(root,path),'ghost tree-folder');line.append(expand,open);row.append(line,children);return row;
}
window.loadFileTree=async()=>{const list=await api('/roots');$('#files-tree').replaceChildren();list.forEach(root=>$('#files-tree').append(fileTreeNode(root,'',root.label)));if(!list.length)$('#files-tree').append(el('p','드라이브 메뉴에서 색인 폴더를 등록하세요.','muted'));};
async function openDirectory(root,path,next=false){
  const version=++directoryVersion;if(!next){directoryOffset=0;directoryRoot=root;directoryPath=path;}$('#files-directory-status').textContent='폴더를 읽고 있습니다…';
  const result=await api('/library/entries?'+new URLSearchParams({root:root.id,path,offset:directoryOffset}));if(version!==directoryVersion)return;
  const crumbs=$('#files-breadcrumbs');crumbs.replaceChildren(button(root.label,()=>openDirectory(root,''),'ghost'));
  const parts=path?path.split('/'):[];parts.forEach((part,i)=>crumbs.append(button(part,()=>openDirectory(root,parts.slice(0,i+1).join('/')),'ghost')));
  const list=$('#files-directory');if(!next)list.replaceChildren();
  result.items.forEach(f=>{const row=el('div',undefined,'file-directory-row');const icon=el('i');icon.dataset.lucide=f.directory?'folder':'file';
    const name=button(f.name,async()=>{if(f.directory)return openDirectory(root,f.path);const query=new URLSearchParams({root:root.id,path:f.path});await showPreview(f,'/api/library/preview?'+query,'/api/library/preview?'+query+'&download=true');},'ghost file-entry');name.prepend(icon);row.append(name,el('small',f.directory?'폴더':fileSize(f.size)),el('small',new Date(f.modified*1000).toLocaleString()));list.append(row);});
  if(window.lucide)lucide.createIcons({attrs:{class:'ui-icon',width:18,height:18,stroke:'currentColor'}});
  $('#files-directory-status').textContent=`${result.total.toLocaleString()}개 항목 · 원본을 변경하지 않는 읽기 전용 탐색`;
  $('#files-directory-more').hidden=directoryOffset+result.items.length>=result.total;
}
action('#files-tree-refresh',loadFileTree);
action('#files-directory-more',async()=>{directoryOffset+=200;await openDirectory(directoryRoot,directoryPath,true);});
action('#files-browse-tab',async()=>{$('#files-browser').hidden=false;$('#files-search-view').hidden=true;await loadFileTree();});
action('#files-search-tab',async()=>{$('#files-browser').hidden=true;$('#files-search-view').hidden=false;await searchFiles();});
