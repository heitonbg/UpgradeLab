"""Bounded raw frametime import. Parsed does not mean authentic."""
import csv,hashlib,io,json,math,statistics
MAX_BYTES=4*1024*1024
MAX_FRAMES=100000
class CaptureError(ValueError):pass

def parse_capture(content,filename):
    if not isinstance(content,str) or len(content.encode('utf-8'))>MAX_BYTES:raise CaptureError('Файл должен быть не больше 4 МиБ')
    metadata={};warnings=[];times=[]
    def clean(meta):
        aliases={'cpu':('CPU','Processor','CpuName','ProcessorName'),'gpu':('GPU','GraphicsCard','GpuName'),'game':('GameName',),'game_version':('GameVersion',),'preset':('Preset',),'resolution':('Resolution',),'os':('OS','OperatingSystem'),'driver':('DriverVersion',),'scene':('Scene',)}
        if not isinstance(meta,dict):return
        for field,keys in aliases.items():
            for key in keys:
                value=meta.get(key)
                if isinstance(value,str) and 1<len(value.strip())<=160 and not any(x in value for x in ('\\','/')):
                    metadata.setdefault(field,value.strip());break
    metric='MsBetweenPresents'
    if filename.lower().endswith('.json'):
        try:data=json.loads(content.lstrip('\ufeff'),parse_constant=lambda _:(_ for _ in ()).throw(CaptureError('NaN/Infinity не допускаются')))
        except (ValueError,RecursionError) as e:raise CaptureError('Не удалось прочитать JSON захвата') from e
        if not isinstance(data,dict):raise CaptureError('Ожидается объект JSON CapFrameX')
        runs=data.get('Runs')
        if not isinstance(runs,list) or len(runs)!=1 or not isinstance(runs[0],dict):raise CaptureError('Поддерживается один прогон CapFrameX (Runs); экспортируйте отдельный захват')
        capture=runs[0].get('CaptureData',{})
        if not isinstance(capture,dict) or not isinstance(capture.get(metric),list):raise CaptureError('В JSON нет массива CaptureData.MsBetweenPresents')
        times=capture[metric]
        clean(data.get('SessionInfo'));clean(data.get('SystemInfo'));clean(data.get('HardwareInfo'));clean(runs[0].get('SessionInfo'));clean(data)
        source='CapFrameX JSON'
    elif filename.lower().endswith('.csv'):
        sample=content.lstrip('\ufeff')
        try:delimiter=csv.Sniffer().sniff(sample[:8192],delimiters=',;\t').delimiter
        except csv.Error:raise CaptureError('Не удалось определить разделитель CSV')
        reader=csv.DictReader(io.StringIO(sample),delimiter=delimiter)
        headers=reader.fieldnames or []
        if len(set(headers))!=len(headers):raise CaptureError('Повторяющиеся столбцы CSV')
        metric=next((key for key in ('MsBetweenPresents','MsBetweenAppStart','FrameTime','CPUFrameTime') if key in headers),None)
        if metric is None:raise CaptureError('Нет поддерживаемого столбца интервала кадров в миллисекундах; сводный FPS или GPUTime не подходят')
        streams=set();frame_types=set()
        try:
            for row in reader:
                if len(times)>=MAX_FRAMES:raise CaptureError('Не больше 100 000 кадров в одном файле')
                if None in row or any(value is None for value in row.values()):raise CaptureError('Повреждённая строка CSV')
                streams.add(tuple(row.get(k,'') for k in ('Application','ProcessID','SwapChainAddress')))
                if len(streams)>1:raise CaptureError('В CSV несколько процессов или swapchain; экспортируйте один поток')
                if row.get('FrameType'):frame_types.add(row['FrameType'])
                times.append(row.get(metric,''));clean(row)
        except csv.Error as e:raise CaptureError('Повреждён CSV') from e
        if len(frame_types)>1:warnings.append('Разные FrameType: проверьте Frame Generation и методику захвата')
        source='PresentMon-compatible CSV'
    else:raise CaptureError('Поддерживаются только CSV и JSON')
    if not times or len(times)>MAX_FRAMES:raise CaptureError('Нужен непустой захват до 100 000 кадров')
    values=[]
    for index,value in enumerate(times):
        if isinstance(value,bool):raise CaptureError('Булево значение вместо frametime')
        try:value=float(str(value).replace(',','.'))
        except (ValueError,TypeError):raise CaptureError('Некорректный интервал кадра')
        if index==0 and value==0:
            warnings.append('Первый нулевой интервал исключён: нет предыдущего кадра');continue
        if not math.isfinite(value) or value<=0 or value>60000:raise CaptureError('Интервалы должны быть конечными положительными числами до 60 секунд')
        values.append(value)
    if len(values)<100:raise CaptureError('Нужно минимум 100 кадров для анализа хвоста 1%')
    mean=statistics.fmean(values);average=1000/mean
    slow_count=math.ceil(len(values)*.01);low=1000/statistics.fmean(sorted(values,reverse=True)[:slow_count])
    if average>2000 or average<.1:raise CaptureError('Средний FPS вне допустимого диапазона 0.1–2000')
    duration=sum(values)/1000
    if duration<10:warnings.append('Короткий захват: меньше 10 секунд')
    if statistics.pstdev(values)/mean<.00001:warnings.append('Практически постоянный frametime: проверьте ограничитель FPS или синтетические данные')
    if sum(v>100 for v in values):warnings.append('Есть кадры дольше 100 мс: проверьте загрузки и фризы; они сохранены в статистике')
    if 'FrameType' not in (headers if filename.lower().endswith('.csv') else []):warnings.append('Тип кадров/Frame Generation автоматически не подтверждён')
    canonical=json.dumps([metric,values],separators=(',',':'),allow_nan=False).encode()
    return {'source':source,'metric':metric,'file_sha256':hashlib.sha256(content.encode()).hexdigest(),
        'fingerprint':hashlib.sha256(canonical).hexdigest(),'metadata':metadata,'average_fps':round(average,3),'one_percent_low':round(low,3),
        'frames':len(values),'duration_seconds':round(duration,3),'minimum_ms':min(values),'maximum_ms':max(values),
        'low_method':'1000 / mean(slowest ceil(1% * N) frame intervals in ms)',
        'warnings':warnings,'authenticity':'unverified','frametimes_ms':values}
