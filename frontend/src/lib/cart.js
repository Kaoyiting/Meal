export const money = n => `NT$ ${n.toLocaleString('zh-TW')}`;
export function configure(item, choices, note='') {
 const labels=[], codes=[]; let extra=0;
 for(const group of item.options){
  const picked=group.multiple ? [...(choices[group.id]||[])].sort((a,b)=>a-b) : [choices[group.id]??0];
  for(const index of picked){const option=group.options[index];if(!option)throw new Error('無效選項');extra+=option.price;labels.push(option.label+(option.price?` +$${option.price}`:''));codes.push(`${group.id}:${index}`);}
 }
 note=note.trim();return {itemId:item.id,name:item.name,unitPrice:item.price+extra,labels,note,key:JSON.stringify([item.id,codes,note])};
}
export function addLine(cart, selection, quantity){
 if(!Number.isInteger(quantity)||quantity<1||quantity>10)throw new Error('數量需為 1 至 10 份');
 const existing=cart.find(line=>line.key===selection.key);
 if(existing&&existing.qty+quantity>10)throw new Error('相同搭配最多 10 份，請調整數量');
 if(existing)existing.qty+=quantity;else cart.push({...selection,qty:quantity});
}
export const totalOf=lines=>lines.reduce((sum,line)=>sum+line.unitPrice*line.qty,0);
