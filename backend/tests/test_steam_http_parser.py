import asyncio,json,unittest
from pathlib import Path
from types import SimpleNamespace as Row
from unittest.mock import patch,AsyncMock
import httpx
from app.services.steam_http import SteamClient,SteamFailure,PinnedBackend,MAX_BYTES,app_id,retry_after
from app.services.steam_parser import split_requirements,parse_requirements,match_level

FIXTURES=Path(__file__).parent/'fixtures/steam'
def fixture(appid=1903340):return json.loads((FIXTURES/f'{appid}.json').read_text(encoding='utf-8'))
def catalog_rows():
    cpus=[Row(id=1,type='CPU',name='Intel Core i7-12700K',raw_score=34230),Row(id=2,type='CPU',name='AMD Ryzen 7 5800X',raw_score=27656),Row(id=3,type='CPU',name='AMD Ryzen 5 5600',raw_score=21819),Row(id=4,type='CPU',name='AMD Ryzen 5 5600X',raw_score=22000)]
    gpus=[Row(id=5,type='GPU',name='GeForce RTX 3060 Ti',raw_score=20283),Row(id=6,type='GPU',name='Radeon RX 6800 XT',raw_score=25000),Row(id=7,type='GPU',name='GeForce RTX 3060 8GB',raw_score=15000),Row(id=8,type='GPU',name='GeForce RTX 3060 12GB',raw_score=17000)]
    return cpus,gpus

class SteamParserTests(unittest.TestCase):
    def test_real_expedition_alternatives_and_explicit_target(self):
        cpus,gpus=catalog_rows();p=parse_requirements(fixture(),cpus,gpus)['recommended']
        self.assertEqual([m['id'] for m in p['cpu_match']['resolved_models']],[1,2])
        self.assertEqual([m['id'] for m in p['gpu_match']['resolved_models']],[5,6])
        self.assertEqual(p['target_fps'],60);self.assertEqual(p['target_resolution'],'1080p');self.assertEqual(p['target_preset'],'high')
        self.assertIsNone(p['rt']);self.assertEqual(p['vram_gb_values'],[8,16])
        self.assertEqual(p['gpu_match']['vram_validation'],'partly_unknown')
    def test_recommended_without_explicit_target_is_not_sixty(self):
        p=split_requirements('Processor: Ryzen 5 5600 Graphics: RTX 3060')
        self.assertIsNone(p['target_fps']);self.assertIsNone(p['target_resolution']);self.assertIsNone(p['target_preset'])
    def test_real_portal_has_no_recommended(self):
        p=parse_requirements(fixture(620));self.assertEqual(p['parsing_status'],'recommended_absent');self.assertIsNone(p['official_target'])
    def test_empty_array_none_fields_are_missing(self):
        for raw in (None,[],{}, {'recommended':None},{'recommended':[]}):
            with self.subTest(raw=raw):self.assertEqual(parse_requirements({'pc_requirements':raw})['recommended']['text'],'')
    def test_suffixes_and_variants_stay_separate(self):
        cpus,gpus=catalog_rows()
        for name,expected in [('AMD Ryzen 5 5600',3),('AMD Ryzen 5 5600X',4)]:
            self.assertEqual(match_level({'cpu':name,'gpu':'RTX 3060 12GB'},cpus,gpus)['cpu_match']['resolved_models'][0]['id'],expected)
        self.assertEqual(match_level({'cpu':'Ryzen 5 5600','gpu':'RTX 3060 12GB'},cpus,gpus)['gpu_match']['resolved_models'][0]['id'],8)
        self.assertFalse(match_level({'cpu':'Ryzen 5 5600','gpu':'RTX 3060 Ti 12GB'},cpus,[gpus[2],gpus[3]])['gpu_match']['resolved_models'])
    def test_known_conflicting_vram_is_not_reassigned(self):
        cpus,gpus=catalog_rows();p=match_level({'cpu':'Ryzen 5 5600','gpu':'RTX 3060 16GB'},cpus,gpus)
        self.assertFalse(p['gpu_match']['resolved_models'])
    def test_laptop_does_not_match_desktop(self):
        cpus,gpus=catalog_rows();p=match_level({'cpu':'Ryzen 5 5600 Laptop','gpu':'RTX 3060 Laptop'},cpus,gpus)
        self.assertFalse(p['cpu_match']['resolved_models']);self.assertFalse(p['gpu_match']['resolved_models'])
    def test_x3d_is_not_plain_x(self):
        cpus,gpus=catalog_rows();p=match_level({'cpu':'Ryzen 7 7800X3D','gpu':'RTX 3060 Ti'},cpus,gpus)
        self.assertFalse(p['cpu_match']['resolved_models'])
    def test_no_scripts_or_default_targets(self):
        p=split_requirements('<script>60 FPS</script><li><strong>Processor:</strong> Ryzen 5 5600</li>')
        self.assertNotIn('60 FPS',p['text']);self.assertIsNone(p['target_fps'])
    def test_conflicting_targets_remain_unknown(self):
        p=split_requirements('Additional Notes: 1080p 60 FPS high settings or 1440p 30 FPS medium settings')
        self.assertIsNone(p['target_fps']);self.assertIsNone(p['target_resolution']);self.assertIsNone(p['target_preset'])
    def test_xtx_is_not_truncated_to_xt(self):
        row=Row(id=55,type='GPU',name='Radeon RX 7900 XT',raw_score=30000)
        p=match_level({'cpu':'','gpu':'Radeon RX 7900 XTX'},[],[row]);self.assertFalse(p['gpu_match']['resolved_models'])

class SteamDeveloperTargetTests(unittest.TestCase):
    def test_all_rendering_conditions_must_be_explicit(self):
        parsed=split_requirements('Additional Notes: 1080p 75 FPS high settings; without ray tracing; native rendering; no frame generation.')
        self.assertEqual(parsed['target_fps'],75);self.assertIs(parsed['rt'],False);self.assertEqual(parsed['upscaling'],'off');self.assertIs(parsed['frame_generation'],False)
    def test_explicit_target_can_scale_existing_gpu_curve_without_becoming_measurement(self):
        from app.services.requirements_anchored_fps import estimate_requirements_anchored_fps
        cpu=Row(id=1,type='CPU',name='Intel Core i7-12700K',raw_score=34230)
        gpu=Row(id=2,type='GPU',name='GeForce RTX 3060 Ti',raw_score=20283)
        profile={'game_id':'test','recommended_requirements':{'cpu':cpu.name,'gpu':gpu.name},'developer_target':{'fps':75,'resolution':'1080p','preset':'high','rt':False,'upscaling':'off','frame_generation':False}}
        reference={'available':True,'data_type':'external_model_estimate','source_name':'PCGameBenchmarks','device_class':'desktop','fps':150,'source_settings':{'resolution':'1080p','preset':'high'}}
        with patch('app.services.external_fps_model.estimate_gpu_fps',return_value={'fps':150}):
            result=estimate_requirements_anchored_fps(profile,cpu,gpu,[cpu],[gpu],reference)
        self.assertEqual(result['scenario_fps'],75)
        self.assertFalse(result['developer_target_used_as_measurement'])
        self.assertEqual(result['data_type'],'experimental_requirements_anchored_estimate')
        profile['developer_target']['rt']=None
        result=estimate_requirements_anchored_fps(profile,cpu,gpu,[cpu],[gpu],reference)
        self.assertEqual(result['scenario_fps'],150)

class SteamClientTests(unittest.IsolatedAsyncioTestCase):
    async def request(self,response):
        async with SteamClient(transport=httpx.MockTransport(lambda req:response)) as c:
            return await c.details(1903340)
    async def test_json_success_and_fixed_endpoint(self):
        seen=[]
        def handler(req):
            seen.append(req);return httpx.Response(200,json={'1903340':{'success':True,'data':fixture()}})
        async with SteamClient(transport=httpx.MockTransport(handler)) as c:
            d=await c.details(1903340);self.assertEqual(d['name'],'Clair Obscur: Expedition 33');self.assertEqual(c.requests,1)
        self.assertEqual(seen[0].url.host,'store.steampowered.com');self.assertEqual(seen[0].url.params['filters'],'basic,pc_requirements')
    async def test_empty_requirements_are_valid_not_sixty(self):
        d=fixture();d['pc_requirements']=[]
        result=await self.request(httpx.Response(200,json={'1903340':{'success':True,'data':d}}));self.assertEqual(result['pc_requirements'],[])
    async def test_status_and_retry_after_no_inline_retries(self):
        for status in (403,429,500,503,302):
            with self.subTest(status=status):
                count=[]
                def handler(req):count.append(req);return httpx.Response(status,headers={'Retry-After':'120','Location':'https://example.com'})
                async with SteamClient(transport=httpx.MockTransport(handler)) as c:
                    with self.assertRaises(SteamFailure) as error:await c.details(1903340)
                    self.assertEqual(error.exception.code,'http_'+str(status));self.assertEqual(error.exception.retry_after,120)
                self.assertEqual(len(count),1)
    async def test_invalid_json(self):
        with self.assertRaisesRegex(SteamFailure,'invalid_json'):await self.request(httpx.Response(200,content=b'{oops',headers={'Content-Type':'application/json'}))
    async def test_oversized(self):
        with self.assertRaisesRegex(SteamFailure,'response_too_large'):await self.request(httpx.Response(200,content=b' '* (MAX_BYTES+1),headers={'Content-Type':'application/json'}))
    async def test_wrong_appid_and_dlc_rejected(self):
        for field,value in [('steam_appid',123),('type','dlc'),('demo_of_app',1903340)]:
            d=fixture();d[field]=value
            with self.assertRaises(SteamFailure):await self.request(httpx.Response(200,json={'1903340':{'success':True,'data':d}}))
    async def test_no_arbitrary_url_or_invalid_appid(self):
        async with SteamClient(transport=httpx.MockTransport(lambda req: self.fail('must not fetch'))) as c:
            for value in ('https://example.com',0,-1,True,'1,2'):
                with self.assertRaises(ValueError):await c.details(value)
            with self.assertRaisesRegex(SteamFailure,'endpoint_denied'):await c._get('/other',{})
            self.assertEqual(c.requests,0)
    async def test_timeout(self):
        def handler(req):raise httpx.ReadTimeout('timeout',request=req)
        async with SteamClient(transport=httpx.MockTransport(handler)) as c:
            with self.assertRaisesRegex(SteamFailure,'timeout'):await c.details(1903340)
    async def test_false_success(self):
        with self.assertRaisesRegex(SteamFailure,'app_not_found'):await self.request(httpx.Response(200,json={'1903340':{'success':False}}))
    async def test_wrong_mime(self):
        with self.assertRaisesRegex(SteamFailure,'invalid_content_type'):await self.request(httpx.Response(200,content=b'{}',headers={'Content-Type':'text/html'}))
    async def test_proxy_environment_is_not_used(self):
        with patch.dict('os.environ',{'HTTPS_PROXY':'http://invalid.example:9999'}):
            await self.request(httpx.Response(200,json={'1903340':{'success':True,'data':fixture()}}))
    async def test_destination_policy_rejects_unapproved_host_without_socket(self):
        backend=PinnedBackend()
        with patch('app.services.steam_http.resolve_public') as dns:
            with self.assertRaises(RuntimeError):await backend.connect_tcp('example.com',443)
            dns.assert_not_called()
