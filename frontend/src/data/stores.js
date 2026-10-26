// 假資料集中管理。正式版由 API 提供，價格由後端驗證。
export const stores = [
{id:'morning',name:'晨光早餐店',category:'早餐店',english:'A GOOD MORNING',symbol:'早',theme:'morning',description:'熱騰騰的蛋餅、酥香吐司，讓一天有個美好的開始。',specialty:'手作蛋餅・烤吐司',items:[
{id:101,name:'經典原味蛋餅',description:'薄煎餅皮包入新鮮雞蛋，搭配鹹甜醬油膏。',price:35},
{id:102,name:'起司玉米蛋餅',description:'香濃起司與甜玉米，外酥內軟的早晨滋味。',price:50},
{id:103,name:'里肌蛋吐司',description:'嫩煎里肌、荷包蛋與清脆生菜，夾入烤吐司。',price:65},
{id:104,name:'薯餅蛋吐司',description:'金黃薯餅搭配雞蛋與番茄醬，酥脆又滿足。',price:55},
{id:105,name:'豆漿',description:'細磨黃豆香氣，350 ml。',price:25}]},
{id:'lunch',name:'每每健康便當',category:'便當店',english:'A PROPER LUNCH',symbol:'飯',theme:'lunch',description:'熟悉的家常味，就是午餐最好的答案。',specialty:'家常主菜・季節時蔬',items:[
{id:201,name:'香烤雞腿飯',description:'香草醃漬雞腿，搭配白飯與三樣季節時蔬。',price:120},
{id:202,name:'厚切排骨飯',description:'經典醬香排骨，搭配滷蛋、清炒青菜與白飯。',price:110},
{id:203,name:'雙菇蔬食飯',description:'香煎雙菇、綿密南瓜與繽紛蔬菜。',price:95},
{id:204,name:'味噌鮭魚飯',description:'味噌烤鮭魚，佐玉子燒、時蔬與白飯。',price:150}]},
{id:'tea',name:'日和茶飲',category:'飲料店',english:'A MOMENT FOR TEA',symbol:'茶',theme:'tea',description:'茶香慢慢展開，讓忙碌的日子，也有一口清爽的空白。',specialty:'原葉好茶・鮮奶茶',items:[
{id:301,name:'茉莉綠茶',description:'淡雅茉莉花香與清爽綠茶，500 ml。',price:35},
{id:302,name:'日和紅茶',description:'清新花果香、溫潤不苦澀，500 ml。',price:35},
{id:303,name:'四季春青茶',description:'清揚花香、自然回甘，500 ml。',price:35},
{id:304,name:'紅茶鮮奶',description:'醇厚紅茶融入鮮奶，500 ml。',price:65},
{id:305,fixedSweetness:true,name:'蜂蜜檸檬',description:'蜂蜜香甜平衡檸檬酸香，500 ml，蜂蜜甜度固定。',price:55}]}];
// 客製化選項：每個 option 的 price 為每份加價，單選預設為第一項。
const opt=(label,price=0)=>({label,price});
const group=(id,label,options,multiple=false)=>({id,label,options,multiple});
stores.forEach(store=>store.items.forEach(item=>{
 if(store.id==='tea') item.options=[
  group('sweet','甜度',item.fixedSweetness?[opt('固定甜度')]:['微糖','無糖','一分糖','半糖','全糖'].map(x=>opt(x))),
  group('ice','冰量',['少冰','正常冰','微冰','去冰'].map(x=>opt(x))),
  group('extra','加料',[opt('珍珠',10),opt('椰果',10)],true)];
 else if(item.id===105)item.options=[group('sweet','甜度',[opt('微糖'),opt('無糖')]),group('temperature','溫度',[opt('溫'),opt('熱'),opt('冰')])];
 else if(store.id==='morning') item.options=[group('spicy','辣度',['不辣','小辣','中辣','大辣'].map(x=>opt(x))),group('extra','加料',[opt('加蛋',15),opt('加起司',15)],true)];
 else item.options=[group('spicy','辣度',['不辣','小辣','中辣','大辣'].map(x=>opt(x))),group('rice','飯量',[opt('正常飯'),opt('少飯'),opt('不飯'),opt('加飯',10)]),group('extra','加料',[opt('加青菜',20),opt('加滷蛋',15)],true)];
}));
