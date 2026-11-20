from pathlib import Path
from datetime import date,datetime
import csv,uuid
import pandas as pd
import streamlit as st

ROOT=Path(__file__).resolve().parent; DATA=ROOT/'data'; DATA.mkdir(exist_ok=True)
STANDARD=DATA/'foods_standard.csv'; CUSTOM=DATA/'foods_custom.csv'; MEALS=DATA/'meals.csv'; ITEMS=DATA/'meal_items.csv'
NUTRI={'kcal':('エネルギー',7,'kcal'),'protein':('たんぱく質',10,'g'),'fat':('脂質',13,'g'),'carbs':('炭水化物',21,'g'),'fiber':('食物繊維',19,'g'),'salt':('食塩相当量',61,'g'),'sodium':('ナトリウム',24,'mg'),'potassium':('カリウム',25,'mg'),'calcium':('カルシウム',26,'mg'),'iron':('鉄',29,'mg'),'zinc':('亜鉛',30,'mg'),'vitamin_d':('ビタミンD',44,'μg'),'vitamin_b1':('ビタミンB1',50,'mg'),'vitamin_b2':('ビタミンB2',51,'mg'),'vitamin_c':('ビタミンC',59,'mg'),'folate':('葉酸',56,'μg')}
FIELDS=['food_code','food_name','category','source']+list(NUTRI)
MEAL_FIELDS=['meal_id','date','meal_type','meal_name','created_at']+list(NUTRI)
ITEM_FIELDS=['meal_id','food_code','food_name','grams']+list(NUTRI)
def readcsv(path,fields):
 if not path.exists():return pd.DataFrame(columns=fields)
 return pd.read_csv(path,dtype=str,keep_default_na=False,encoding='utf-8-sig')
def append(path,fields,record):
 new=not path.exists() or path.stat().st_size==0
 with path.open('a',newline='',encoding='utf-8-sig') as f:
  w=csv.DictWriter(f,fieldnames=fields);w.writeheader() if new else None;w.writerow({k:record.get(k,'') for k in fields})
def save(path,fields,df):df.reindex(columns=fields).to_csv(path,index=False,encoding='utf-8-sig')
def number(value):
 v=str(value).strip().replace('*','').replace('(','').replace(')','')
 if v in ('','-','Tr','tr','…','－','NaN','nan'):return None
 try:return float(v)
 except ValueError:return None
def load_foods():
 raw=pd.read_csv(STANDARD,dtype=str,keep_default_na=False,encoding='utf-8-sig')
 cols=list(raw.columns);out=[]
 for _,r in raw.iterrows():
  x={'food_code':r.iloc[1],'food_name':r.iloc[3],'category':r.iloc[0],'source':'日本食品標準成分表2023'}
  for k,(_,col,unit) in NUTRI.items():x[k]=r.iloc[col-1]
  out.append(x)
 official=pd.DataFrame(out,columns=FIELDS)
 custom=readcsv(CUSTOM,FIELDS)
 return pd.concat([official,custom],ignore_index=True)
def scaled(food,grams):
 return {k:(None if number(food[k]) is None else number(food[k])*grams/100) for k in NUTRI}
def totals(items):
 result={}
 for k in NUTRI:
  values=[x['nutrients'][k] for x in items]
  result[k]=sum(v for v in values if v is not None) if all(v is not None for v in values) else None
 return result
def fmt(v):return '不明' if v is None else f'{v:,.2f}'
st.set_page_config(page_title='栄養計算・食事記録',layout='wide')
st.title('栄養計算・食事記録')
st.caption('日本食品標準成分表（八訂）増補2023年｜可食部100g当たり｜CSV保存')
foods=load_foods(); labels={i:f"{r['food_name']} [{r['food_code']}] ({'独自登録' if r['source']=='custom' else '標準'})" for i,r in foods.iterrows()}
calc,manage,history=st.tabs(['栄養計算','食品マスター管理','食事履歴'])
with calc:
 st.subheader('材料と重量を指定')
 if 'basket' not in st.session_state:st.session_state.basket=[]
 q=st.text_input('食品名検索（部分一致）',placeholder='例：こめ、鶏、ブロッコリー')
 filtered=[i for i in labels if q.strip() in labels[i]] if q.strip() else list(labels)[:150]
 if not filtered:st.warning('該当する食品がありません')
 else:
  selected=st.selectbox('食品を選択',filtered,format_func=lambda i:labels[i])
  grams=st.number_input('使用量（可食部 g）',min_value=0.1,value=100.0,step=10.0)
  if st.button('材料を追加',type='primary'):
   r=foods.loc[selected].to_dict();st.session_state.basket.append({'food':r,'grams':grams,'nutrients':scaled(r,grams)});st.rerun()
 if st.session_state.basket:
  for j,item in enumerate(st.session_state.basket):
   a,b=st.columns([5,1]);a.write(f"{item['food']['food_name']}　{item['grams']:g} g")
   if b.button('削除',key=f'remove_{j}'):
    st.session_state.basket.pop(j);st.rerun()
  total=totals(st.session_state.basket)
  st.metric('エネルギー',fmt(total['kcal'])+' kcal')
  st.dataframe(pd.DataFrame([{'栄養素':name,'合計':fmt(total[k]),'単位':unit} for k,(name,_,unit) in NUTRI.items()]),hide_index=True,use_container_width=True)
  st.caption('不明は未収載・未測定等を含みます。材料に不明値があれば合計も不明として表示します。')
  with st.form('confirm'):
   day=st.date_input('食事日',date.today());kind=st.selectbox('食事区分',['朝食','昼食','夕食','間食','その他']);mealname=st.text_input('料理名・メモ')
   submit=st.form_submit_button('この内容で確定・CSV保存',type='primary')
  if submit:
   mid=uuid.uuid4().hex;row={'meal_id':mid,'date':day.isoformat(),'meal_type':kind,'meal_name':mealname,'created_at':datetime.now().isoformat(timespec='seconds'),**{k:'' if v is None else v for k,v in total.items()}}
   append(MEALS,MEAL_FIELDS,row)
   for item in st.session_state.basket:
    append(ITEMS,ITEM_FIELDS,{'meal_id':mid,'food_code':item['food']['food_code'],'food_name':item['food']['food_name'],'grams':item['grams'],**{k:'' if v is None else v for k,v in item['nutrients'].items()}})
   st.session_state.basket=[];st.success('食事を保存しました。');st.rerun()
with manage:
 st.subheader('独自食品の登録・編集・削除')
 st.info('栄養値は可食部100g当たりで入力します。未記載項目は空欄のままにしてください。')
 own=readcsv(CUSTOM,FIELDS)
 mode=st.radio('操作',['新規登録','編集','削除'],horizontal=True)
 target=None
 if mode!='新規登録':
  if own.empty:st.warning('独自食品がまだありません')
  else:target=st.selectbox('対象食品',range(len(own)),format_func=lambda i:f"{own.iloc[i]['food_name']} [{own.iloc[i]['food_code']}]")
 if mode!='削除' and (mode=='新規登録' or target is not None):
  previous=own.iloc[target].to_dict() if target is not None else {}
  with st.form('food_form'):
   name=st.text_input('食品名',value=previous.get('food_name',''))
   category=st.text_input('分類',value=previous.get('category','独自登録'))
   vals={}
   for k,(title,_,unit) in NUTRI.items():
    v=previous.get(k,'');vals[k]=st.text_input(f'{title} ({unit}/100g)',value='' if v is None else str(v),key=f'edit_{k}')
   done=st.form_submit_button('保存',type='primary')
  if done:
   if not name.strip():st.error('食品名を入力してください')
   elif any(v.strip() and (number(v) is None or number(v)<0) for v in vals.values()):st.error('栄養値は0以上の数値か空欄にしてください')
   else:
    record={'food_code':previous.get('food_code','U'+uuid.uuid4().hex[:10]),'food_name':name.strip(),'category':category,'source':'custom',**vals}
    if target is None:append(CUSTOM,FIELDS,record)
    else:
     for k,v in record.items():own.loc[target,k]=v
     save(CUSTOM,FIELDS,own)
    st.success('保存しました');st.rerun()
 if mode=='削除' and target is not None:
  st.warning('食品を削除しても、過去の食事記録は残ります。')
  if st.button('選択した独自食品を削除',type='primary'):
   save(CUSTOM,FIELDS,own.drop(own.index[target]));st.rerun()
with history:
 meals=readcsv(MEALS,MEAL_FIELDS);items=readcsv(ITEMS,ITEM_FIELDS)
 if meals.empty:st.info('食事記録はまだありません')
 else:
  st.dataframe(meals.iloc[::-1],use_container_width=True,hide_index=True)
  chosen=st.selectbox('明細表示・削除対象',list(meals.index[::-1]),format_func=lambda i:f"{meals.loc[i,'date']} {meals.loc[i,'meal_type']} {meals.loc[i,'meal_name']} ({meals.loc[i,'meal_id'][:8]})")
  mid=meals.loc[chosen,'meal_id'];st.dataframe(items[items['meal_id']==mid],hide_index=True,use_container_width=True)
  if st.button('選択した食事記録を削除'):
   save(MEALS,MEAL_FIELDS,meals[meals['meal_id']!=mid]);save(ITEMS,ITEM_FIELDS,items[items['meal_id']!=mid]);st.rerun()
  st.download_button('食事履歴CSVをダウンロード',meals.to_csv(index=False).encode('utf-8-sig'),'meals_export.csv','text/csv')
  st.download_button('材料明細CSVをダウンロード',items.to_csv(index=False).encode('utf-8-sig'),'meal_items_export.csv','text/csv')
