from pathlib import Path
from datetime import datetime, date, time
import csv
import uuid
import pandas as pd
import streamlit as st

st.set_page_config(page_title='栄養・血糖・体重記録', layout='wide')
ROOT = Path(__file__).resolve().parent
DATA = ROOT / 'data'
DATA.mkdir(exist_ok=True)
STANDARD = DATA / 'foods_standard.csv'
CUSTOM = DATA / 'foods_custom.csv'
MEALS = DATA / 'meals.csv'
ITEMS = DATA / 'meal_items.csv'
WEIGHTS = DATA / 'weight_records.csv'
GLUCOSE = DATA / 'glucose_records.csv'

# 日本食品標準成分表（八訂）増補2023年の列名
NUTRI = {
    'kcal': ('エネルギー', 'kcal', 'ENERC_KCAL'),
    'protein': ('たんぱく質', 'g', 'PROT-'),
    'fat': ('脂質', 'g', 'FAT-'),
    'carbs': ('炭水化物', 'g', 'CHOCDF-'),
    'sugar': ('糖質（利用可能炭水化物）', 'g', 'CHOAVLM'),
    'fiber': ('食物繊維', 'g', 'FIB-'),
    'salt': ('食塩相当量', 'g', 'NACL_EQ'),
    'sodium': ('ナトリウム', 'mg', 'NA'),
    'potassium': ('カリウム', 'mg', 'K'),
    'calcium': ('カルシウム', 'mg', 'CA'),
    'iron': ('鉄', 'mg', 'FE'),
    'zinc': ('亜鉛', 'mg', 'ZN'),
    'vitamin_d': ('ビタミンD', 'μg', 'VITD'),
    'vitamin_b1': ('ビタミンB1', 'mg', 'THIA'),
    'vitamin_b2': ('ビタミンB2', 'mg', 'RIBF'),
    'vitamin_c': ('ビタミンC', 'mg', 'VITC'),
    'folate': ('葉酸', 'μg', 'FOL'),
}
KEYS = list(NUTRI)
FOOD_FIELDS = ['food_code', 'food_name', 'category', 'source', 'sugar_method'] + KEYS
MEAL_FIELDS = ['meal_id', 'date', 'meal_datetime', 'meal_type', 'meal_name', 'servings', 'created_at'] + KEYS
ITEM_FIELDS = ['meal_id', 'food_code', 'food_name', 'grams'] + KEYS
WEIGHT_FIELDS = ['id', 'date', 'weight_kg', 'body_fat_pct', 'memo']
GLUCOSE_FIELDS = ['id', 'datetime', 'glucose_mg_dl', 'timing', 'meal_id', 'memo']


def read_csv(path, fields):
    if not path.exists() or path.stat().st_size == 0:
        return pd.DataFrame(columns=fields)
    df = pd.read_csv(path, dtype=str, keep_default_na=False, encoding='utf-8-sig')
    for key in fields:
        if key not in df.columns:
            df[key] = ''
    return df[fields]


def save_csv(path, fields, df):
    df.reindex(columns=fields).to_csv(path, index=False, encoding='utf-8-sig')


def append_csv(path, fields, record):
    first = not path.exists() or path.stat().st_size == 0
    with path.open('a', newline='', encoding='utf-8-sig') as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        if first:
            writer.writeheader()
        writer.writerow({key: record.get(key, '') for key in fields})


def num(value):
    value = str(value).strip().replace('*', '').replace('（', '(').replace('）', ')')
    if value in ('', '-', '－', 'Tr', 'tr', '…', 'nan', 'NaN', 'None'):
        return None
    try:
        return float(value.strip('()'))
    except ValueError:
        return None


def display(value, unit=''):
    return '不明' if value is None or pd.isna(value) else f'{value:,.2f} {unit}'.strip()


@st.cache_data(show_spinner='食品成分表を読み込んでいます')
def official_foods(path, modified):
    raw = pd.read_csv(path, dtype=str, keep_default_na=False, encoding='utf-8-sig')
    records = []
    for _, r in raw.iterrows():
        record = {
            'food_code': r.get('food_code', ''),
            'food_name': r.get('food_name', ''),
            'category': r.get('food_group', ''),
            'source': '日本食品標準成分表（八訂）増補2023年',
            'sugar_method': '利用可能炭水化物（質量計）',
        }
        for key, (_, _, col) in NUTRI.items():
            record[key] = r.get(col, '')
        # 糖質相当の直接値がない場合のみ、差引値を参考値として採用
        if num(record['sugar']) is None:
            carb, fiber = num(record['carbs']), num(record['fiber'])
            if carb is not None and fiber is not None:
                record['sugar'] = str(max(0, carb - fiber))
                record['sugar_method'] = '参考値（炭水化物－食物繊維）'
            else:
                record['sugar_method'] = '不明'
        records.append(record)
    return pd.DataFrame(records, columns=FOOD_FIELDS)


def load_foods():
    if not STANDARD.exists():
        st.error('data/foods_standard.csv がありません。Ver.3のdataフォルダを配置してください。')
        st.stop()
    official = official_foods(str(STANDARD), STANDARD.stat().st_mtime_ns)
    custom = read_csv(CUSTOM, FOOD_FIELDS)
    return pd.concat([official, custom], ignore_index=True)


def scale(food, grams):
    return {key: (None if num(food.get(key, '')) is None else num(food[key]) * grams / 100) for key in KEYS}


def total_nutrients(basket):
    output = {}
    for key in KEYS:
        values = [item['nutrients'][key] for item in basket]
        output[key] = sum(values) if all(value is not None for value in values) else None
    return output


def numeric_row(values, divisor=1):
    return {key: '' if values[key] is None else values[key] / divisor for key in KEYS}


def download_csv(label, df, filename, key):
    st.download_button(label, df.to_csv(index=False).encode('utf-8-sig'), filename, 'text/csv', key=key)


st.title('栄養計算・食事・血糖値・体重管理')
st.caption('食品成分：日本食品標準成分表（八訂）増補2023年｜保存方式：CSV')
foods = load_foods()
page = st.sidebar.radio('メニュー', ['栄養計算・食事登録', '食事履歴', '血糖値記録・分析', '体重記録', '統合分析', '独自食品管理', 'CSVバックアップ'])

if page == '栄養計算・食事登録':
    st.header('料理の栄養計算')
    if 'basket' not in st.session_state:
        st.session_state.basket = []
    query = st.text_input('食品名・食品番号で検索', placeholder='例：ごはん、鶏、1001')
    if query.strip():
        matches = foods[foods['food_name'].str.contains(query.strip(), case=False, regex=False, na=False) | foods['food_code'].str.contains(query.strip(), case=False, regex=False, na=False)]
    else:
        matches = foods.head(150)
    if matches.empty:
        st.warning('該当する食品がありません')
    else:
        indices = matches.index.tolist()
        selected = st.selectbox('食品', indices, format_func=lambda i: f"{foods.at[i, 'food_name']} [{foods.at[i, 'food_code']}]" )
        grams = st.number_input('使用量（可食部 g）', min_value=0.1, value=100.0, step=10.0)
        if st.button('材料を追加', type='primary'):
            food = foods.loc[selected].to_dict()
            st.session_state.basket.append({'food': food, 'grams': grams, 'nutrients': scale(food, grams)})
            st.rerun()
    basket = st.session_state.basket
    if basket:
        st.subheader('材料一覧')
        for i, item in enumerate(basket):
            a, b = st.columns([5, 1])
            a.write(f"{item['food']['food_name']}　{item['grams']:g} g")
            if b.button('削除', key=f'del_basket_{i}'):
                basket.pop(i)
                st.rerun()
        servings = st.number_input('何人で食べますか？（均等に分ける人数）', min_value=1, max_value=100, value=1, step=1)
        total = total_nutrients(basket)
        a, b = st.columns(2)
        a.metric('料理全体のエネルギー', display(total['kcal'], 'kcal'))
        b.metric('1人分のエネルギー', display(None if total['kcal'] is None else total['kcal'] / servings, 'kcal'))
        st.dataframe(pd.DataFrame([{'栄養素': title, '料理全体': display(total[key], unit), '1人分': display(None if total[key] is None else total[key] / servings, unit)} for key, (title, unit, _) in NUTRI.items()]), hide_index=True, use_container_width=True)
        methods = sorted(set(item['food'].get('sugar_method', '') for item in basket))
        st.caption('糖質の算出方法：' + '／'.join(m for m in methods if m))
        st.caption('「不明」は0ではありません。材料に不明な成分値が含まれる場合、その成分の合計は不明と表示します。')
        with st.form('save_meal'):
            c1, c2 = st.columns(2)
            day = c1.date_input('食事日', value=date.today())
            tm = c2.time_input('食事開始時刻', value=datetime.now().time().replace(second=0, microsecond=0))
            kind = st.selectbox('食事区分', ['朝食', '昼食', '夕食', '間食', 'その他'])
            meal_name = st.text_input('料理名・メモ')
            submitted = st.form_submit_button('1人分として食事を確定・保存', type='primary')
        if submitted:
            mid = uuid.uuid4().hex
            meal_dt = datetime.combine(day, tm).isoformat(timespec='seconds')
            append_csv(MEALS, MEAL_FIELDS, {'meal_id': mid, 'date': day.isoformat(), 'meal_datetime': meal_dt, 'meal_type': kind, 'meal_name': meal_name, 'servings': servings, 'created_at': datetime.now().isoformat(timespec='seconds'), **numeric_row(total, servings)})
            for item in basket:
                append_csv(ITEMS, ITEM_FIELDS, {'meal_id': mid, 'food_code': item['food']['food_code'], 'food_name': item['food']['food_name'], 'grams': item['grams'], **numeric_row(item['nutrients'], servings)})
            st.session_state.basket = []
            st.success('食事を保存しました。栄養値は1人分です。')
            st.rerun()

elif page == '食事履歴':
    st.header('食事履歴')
    meals = read_csv(MEALS, MEAL_FIELDS)
    items = read_csv(ITEMS, ITEM_FIELDS)
    if meals.empty:
        st.info('食事履歴がありません')
    else:
        st.dataframe(meals.iloc[::-1], hide_index=True, use_container_width=True)
        selected = st.selectbox('詳細表示・削除する食事', meals.index[::-1].tolist(), format_func=lambda i: f"{meals.at[i, 'meal_datetime'] or meals.at[i, 'date']} {meals.at[i, 'meal_type']} {meals.at[i, 'meal_name']}")
        mid = meals.at[selected, 'meal_id']
        st.dataframe(items[items['meal_id'] == mid], hide_index=True, use_container_width=True)
        st.warning('食事を削除すると、その食事に紐付く血糖記録は「食事未紐付け」に変更されます。血糖測定自体は残ります。')
        if st.checkbox('この食事の削除を確認') and st.button('食事を削除'):
            save_csv(MEALS, MEAL_FIELDS, meals[meals['meal_id'] != mid])
            save_csv(ITEMS, ITEM_FIELDS, items[items['meal_id'] != mid])
            glucose = read_csv(GLUCOSE, GLUCOSE_FIELDS)
            glucose.loc[glucose['meal_id'] == mid, 'meal_id'] = ''
            if GLUCOSE.exists():
                save_csv(GLUCOSE, GLUCOSE_FIELDS, glucose)
            st.rerun()
        download_csv('食事CSVをダウンロード', meals, 'meals.csv', 'export_meals')
        download_csv('材料CSVをダウンロード', items, 'meal_items.csv', 'export_items')

elif page == '血糖値記録・分析':
    st.header('血糖値記録・分析')
    st.caption('指先採血などの手入力を想定。食後時間は食事開始時刻から計算します。')
    meals = read_csv(MEALS, MEAL_FIELDS)
    with st.form('glucose_form'):
        c1, c2 = st.columns(2)
        day = c1.date_input('測定日', date.today())
        tm = c2.time_input('測定時刻', datetime.now().time().replace(second=0, microsecond=0))
        glucose_value = st.number_input('血糖値（mg/dL）', min_value=1, max_value=1000, value=100, step=1)
        timing = st.selectbox('測定タイミング', ['食前', '食後', '空腹時', '就寝前', 'その他'])
        meal_choices = [''] + meals['meal_id'].tolist()
        meal_labels = {r['meal_id']: f"{r['meal_datetime'] or r['date']} {r['meal_type']} {r['meal_name']}" for _, r in meals.iterrows()}
        linked_meal = st.selectbox('関連する食事（任意）', meal_choices, format_func=lambda mid: '紐付けなし' if not mid else meal_labels.get(mid, mid))
        memo = st.text_input('メモ（運動・体調・服薬など）')
        submitted = st.form_submit_button('血糖値を保存', type='primary')
    if submitted:
        measured = datetime.combine(day, tm)
        valid = True
        if linked_meal:
            row = meals[meals['meal_id'] == linked_meal].iloc[0]
            meal_dt = pd.to_datetime(row['meal_datetime'], errors='coerce')
            if pd.notna(meal_dt):
                if timing == '食後' and measured < meal_dt.to_pydatetime():
                    st.error('食後の測定時刻が食事開始より前です。時刻または食事を確認してください。')
                    valid = False
                elif timing == '食前' and measured > meal_dt.to_pydatetime():
                    st.error('食前の測定時刻が食事開始より後です。時刻または食事を確認してください。')
                    valid = False
        if valid:
            append_csv(GLUCOSE, GLUCOSE_FIELDS, {'id': uuid.uuid4().hex, 'datetime': measured.isoformat(timespec='seconds'), 'glucose_mg_dl': glucose_value, 'timing': timing, 'meal_id': linked_meal, 'memo': memo})
            st.success('血糖値を保存しました')
    glucose = read_csv(GLUCOSE, GLUCOSE_FIELDS)
    if glucose.empty:
        st.info('血糖値の記録がありません')
    else:
        glucose['measured_at'] = pd.to_datetime(glucose['datetime'], errors='coerce')
        glucose['value'] = pd.to_numeric(glucose['glucose_mg_dl'], errors='coerce')
        valid = glucose.dropna(subset=['measured_at', 'value']).sort_values('measured_at')
        if not valid.empty:
            c1, c2, c3 = st.columns(3)
            c1.metric('平均（全測定）', display(valid['value'].mean(), 'mg/dL'))
            c2.metric('最高（全測定）', display(valid['value'].max(), 'mg/dL'))
            c3.metric('最低（全測定）', display(valid['value'].min(), 'mg/dL'))
            st.line_chart(valid.set_index('measured_at')['value'])
            st.caption('食前・食後など測定条件が混在するため、全測定平均は診断指標ではありません。')
            st.subheader('食事ごとの食前後比較')
            comparisons = []
            for mid, group in valid[valid['meal_id'] != ''].groupby('meal_id'):
                meal_row = meals[meals['meal_id'] == mid]
                if meal_row.empty:
                    continue
                meal = meal_row.iloc[0]
                meal_dt = pd.to_datetime(meal['meal_datetime'], errors='coerce')
                if pd.isna(meal_dt):
                    continue
                before = group[(group['timing'] == '食前') & (group['measured_at'] <= meal_dt) & (group['measured_at'] >= meal_dt - pd.Timedelta(minutes=30))]
                after = group[(group['timing'] == '食後') & (group['measured_at'] >= meal_dt + pd.Timedelta(minutes=30)) & (group['measured_at'] <= meal_dt + pd.Timedelta(minutes=150))]
                if before.empty or after.empty:
                    continue
                baseline = before.iloc[-1]['value']
                for _, measurement in after.iterrows():
                    minutes = (measurement['measured_at'] - meal_dt).total_seconds() / 60
                    comparisons.append({'食事日時': meal_dt, '料理名': meal['meal_name'], '糖質(g/人)': num(meal['sugar']), '炭水化物(g/人)': num(meal['carbs']), '食後経過(分)': round(minutes), '食前(mg/dL)': baseline, '食後(mg/dL)': measurement['value'], '変化量(mg/dL)': measurement['value'] - baseline})
            if comparisons:
                comp = pd.DataFrame(comparisons)
                st.dataframe(comp, hide_index=True, use_container_width=True)
                st.scatter_chart(comp.dropna(subset=['糖質(g/人)']), x='糖質(g/人)', y='変化量(mg/dL)') if comp['糖質(g/人)'].notna().any() else st.info('糖質データがないため散布図を表示できません。')
                st.caption('食前は食事開始30分前以内、食後は開始30〜150分後の実測値を対象とします。食後の経過時間が異なるデータの単純比較には注意してください。')
            else:
                st.info('同じ食事に紐付いた食前30分以内と食後30〜150分の測定がそろうと比較を表示します。')
        st.subheader('測定履歴')
        st.dataframe(glucose[GLUCOSE_FIELDS].iloc[::-1], hide_index=True, use_container_width=True)
        options = glucose.iloc[::-1]
        selected = st.selectbox('削除対象', options['id'].tolist(), format_func=lambda rid: f"{options.loc[options['id'] == rid, 'datetime'].iloc[0]} / {options.loc[options['id'] == rid, 'glucose_mg_dl'].iloc[0]} mg/dL")
        if st.checkbox('血糖記録の削除を確認') and st.button('選択した血糖記録を削除'):
            save_csv(GLUCOSE, GLUCOSE_FIELDS, glucose[glucose['id'] != selected])
            st.rerun()
        download_csv('血糖値CSVをダウンロード', glucose[GLUCOSE_FIELDS], 'glucose_records.csv', 'export_glucose')

elif page == '体重記録':
    st.header('体重記録')
    with st.form('weight_form'):
        day = st.date_input('測定日', date.today())
        weight = st.number_input('体重（kg）', min_value=1.0, max_value=400.0, value=60.0, step=0.1)
        fat = st.number_input('体脂肪率（%）※0は未入力', min_value=0.0, max_value=100.0, value=0.0, step=0.1)
        memo = st.text_input('メモ')
        submitted = st.form_submit_button('体重を保存', type='primary')
    if submitted:
        append_csv(WEIGHTS, WEIGHT_FIELDS, {'id': uuid.uuid4().hex, 'date': day.isoformat(), 'weight_kg': weight, 'body_fat_pct': fat if fat > 0 else '', 'memo': memo})
        st.success('体重を保存しました')
    df = read_csv(WEIGHTS, WEIGHT_FIELDS)
    if df.empty:
        st.info('体重記録がありません')
    else:
        df['day'] = pd.to_datetime(df['date'], errors='coerce')
        df['weight'] = pd.to_numeric(df['weight_kg'], errors='coerce')
        valid = df.dropna(subset=['day', 'weight']).sort_values('day')
        if not valid.empty:
            st.metric('最新体重', display(valid.iloc[-1]['weight'], 'kg'))
            st.metric('初回比', display(valid.iloc[-1]['weight'] - valid.iloc[0]['weight'], 'kg'))
            st.line_chart(valid.groupby('day')['weight'].last())
            fat_series = pd.to_numeric(valid['body_fat_pct'], errors='coerce')
            if fat_series.notna().any():
                st.subheader('体脂肪率')
                st.line_chart(valid.assign(fat=fat_series).dropna(subset=['fat']).groupby('day')['fat'].last())
        st.dataframe(df[WEIGHT_FIELDS].iloc[::-1], hide_index=True, use_container_width=True)
        selected = st.selectbox('削除対象', df.iloc[::-1]['id'].tolist(), format_func=lambda rid: f"{df.loc[df['id'] == rid, 'date'].iloc[0]} / {df.loc[df['id'] == rid, 'weight_kg'].iloc[0]} kg")
        if st.checkbox('体重記録の削除を確認') and st.button('選択した体重記録を削除'):
            save_csv(WEIGHTS, WEIGHT_FIELDS, df[df['id'] != selected])
            st.rerun()
        download_csv('体重CSVをダウンロード', df[WEIGHT_FIELDS], 'weight_records.csv', 'export_weight')

elif page == '統合分析':
    st.header('食事・血糖値・体重の統合分析')
    meals = read_csv(MEALS, MEAL_FIELDS)
    weights = read_csv(WEIGHTS, WEIGHT_FIELDS)
    glucose = read_csv(GLUCOSE, GLUCOSE_FIELDS)
    days = st.selectbox('集計期間', [7, 14, 30, 90, 365], index=2)
    start = pd.Timestamp(date.today()) - pd.Timedelta(days=days - 1)
    if not meals.empty:
        meals['day'] = pd.to_datetime(meals['date'], errors='coerce')
        recent = meals[meals['day'] >= start].copy()
        for key in ['kcal', 'carbs', 'sugar', 'fiber']:
            recent[key] = pd.to_numeric(recent[key], errors='coerce')
        if not recent.empty:
            daily = recent.groupby('day')[['kcal', 'carbs', 'sugar', 'fiber']].sum(min_count=1)
            st.subheader('日別摂取栄養量（記録済みの食事のみ）')
            st.line_chart(daily[['kcal']])
            st.line_chart(daily[['carbs', 'sugar', 'fiber']])
            st.caption('食事を記録していない日の摂取量は0とみなしません。')
    if not weights.empty:
        weights['day'] = pd.to_datetime(weights['date'], errors='coerce')
        weights['value'] = pd.to_numeric(weights['weight_kg'], errors='coerce')
        recent = weights[(weights['day'] >= start)].dropna(subset=['day', 'value'])
        if not recent.empty:
            st.subheader('体重推移')
            st.line_chart(recent.groupby('day')['value'].last())
    if not glucose.empty:
        glucose['dt'] = pd.to_datetime(glucose['datetime'], errors='coerce')
        glucose['value'] = pd.to_numeric(glucose['glucose_mg_dl'], errors='coerce')
        recent = glucose[(glucose['dt'] >= start)].dropna(subset=['dt', 'value'])
        if not recent.empty:
            st.subheader('血糖値推移（実測値）')
            st.line_chart(recent.sort_values('dt').set_index('dt')['value'])
    st.caption('異なる測定条件や記録不足に注意してください。グラフ上の関連は因果関係や診断を意味しません。')

elif page == '独自食品管理':
    st.header('独自食品の登録・編集・削除')
    st.info('栄養値は可食部100g当たりです。未入力の栄養素は不明として扱います。')
    custom = read_csv(CUSTOM, FOOD_FIELDS)
    mode = st.radio('操作', ['新規登録', '編集', '削除'], horizontal=True)
    selected = None
    if mode != '新規登録':
        if custom.empty:
            st.info('独自食品がありません')
        else:
            selected = st.selectbox('対象食品', custom.index.tolist(), format_func=lambda i: f"{custom.at[i, 'food_name']} [{custom.at[i, 'food_code']}]")
    if mode != '削除' and (mode == '新規登録' or selected is not None):
        old = custom.loc[selected].to_dict() if selected is not None else {}
        with st.form('custom_food_form'):
            name = st.text_input('食品名', value=old.get('food_name', ''))
            category = st.text_input('分類', value=old.get('category', '独自登録'))
            values = {}
            for key, (title, unit, _) in NUTRI.items():
                values[key] = st.text_input(f'{title}（{unit}/100g）', value=str(old.get(key, '')), key=f'custom_{key}')
            submitted = st.form_submit_button('食品を保存', type='primary')
        if submitted:
            if not name.strip():
                st.error('食品名を入力してください')
            elif any(v.strip() and (num(v) is None or num(v) < 0) for v in values.values()):
                st.error('栄養値は0以上の数値または空欄にしてください')
            else:
                record = {'food_code': old.get('food_code', 'U' + uuid.uuid4().hex[:10]), 'food_name': name.strip(), 'category': category, 'source': 'custom', 'sugar_method': '独自入力', **values}
                if selected is None:
                    append_csv(CUSTOM, FOOD_FIELDS, record)
                else:
                    for key, value in record.items():
                        custom.at[selected, key] = value
                    save_csv(CUSTOM, FOOD_FIELDS, custom)
                st.success('保存しました')
                st.rerun()
    if mode == '削除' and selected is not None:
        if st.checkbox('独自食品の削除を確認') and st.button('食品を削除'):
            save_csv(CUSTOM, FOOD_FIELDS, custom.drop(index=selected))
            st.rerun()
    if not custom.empty:
        download_csv('独自食品CSVをダウンロード', custom, 'foods_custom.csv', 'export_custom')

elif page == 'CSVバックアップ':
    st.header('CSVバックアップ・復元')
    st.warning('Streamlit Community Cloudではアプリ内CSVの永続保存は保証されません。定期的にバックアップしてください。また、ログイン制御がない公開アプリでは個人の健康記録が他の利用者に見える可能性があります。')
    files = {'独自食品': (CUSTOM, FOOD_FIELDS), '食事履歴': (MEALS, MEAL_FIELDS), '食事材料': (ITEMS, ITEM_FIELDS), '血糖値': (GLUCOSE, GLUCOSE_FIELDS), '体重': (WEIGHTS, WEIGHT_FIELDS)}
    for label, (path, fields) in files.items():
        with st.expander(label):
            df = read_csv(path, fields)
            download_csv(f'{label}をダウンロード', df, path.name, f'backup_{path.name}')
            upload = st.file_uploader(f'{label}のCSVを復元（現在の内容を置き換え）', type='csv', key=f'upload_{path.name}')
            if upload is not None:
                try:
                    restored = pd.read_csv(upload, dtype=str, keep_default_na=False, encoding='utf-8-sig')
                    if not set(fields).issubset(restored.columns):
                        st.error('必要な列が不足しています：' + ', '.join(sorted(set(fields) - set(restored.columns))))
                    elif st.checkbox('既存の内容を上書きすることを確認', key=f'confirm_{path.name}') and st.button('復元を実行', key=f'restore_{path.name}'):
                        save_csv(path, fields, restored)
                        st.success('復元しました')
                        st.rerun()
                except (UnicodeError, pd.errors.ParserError, ValueError) as exc:
                    st.error(f'CSVを読み込めません：{exc}')
