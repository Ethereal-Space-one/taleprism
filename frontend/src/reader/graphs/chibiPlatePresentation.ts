import type { PlatePresentationRecipe } from '../platePresentation'

// Descriptions retain only observable content from the checked-in per-image
// observations in examples/chibi/visual-review-v0.2.0.json (2026-11-12).
// No new visual inspection, historical certification, or creator approval is
// implied. Asset hashes prevent applying these words to replacement artwork.
export const chibiPlatePresentation = {
  canonicalHash: 'ad97df377de9a9f5f2680253666ec6d9a6d2b8be055ee94a92643a4b16043341',
  plates: [
    {
      id: 'river-overlook',
      imageAsset: 'da59592b-3675-45ae-aefe-867b01d0a2e3',
      imageHash: 'e615364cdee1f0fad4236afbf44aa1d5b0bd338cba14acaa01c2cf2506042c07',
      sourceStart: 0,
      sourceEnd: 63,
      evidence: '三江口周瑜縱火',
      visualDescription:
        '周瑜着绛袍、戴冠，侧身站在岩岸上，抿唇望向密集舰船；随从在他右后方，江面尚无火光。',
    },
    {
      id: 'sickbed-dialogue',
      imageAsset: 'eb1e632b-c841-4062-9013-20f3e33c6e01',
      imageHash: 'fc5edfb4d06e649857d3fb8a81426d5c8d21f89b92c3559154564a971ce22834',
      sourceStart: 993,
      sourceEnd: 1503,
      evidence: '瑜聞失色，乃作呻吟之聲。',
      visualDescription:
        '帐内两人近景。孔明在左侧微笑、直视周瑜；周瑜在右侧木床上半卧，蹙眉握被。枕被、铜灯和小杯位于床边。',
    },
    {
      id: 'altar-assembly',
      imageAsset: 'c6d54ad9-b541-4806-af07-adaf5c0023b0',
      imageHash: '7a8d75214742e019ad5d1f3cd4f6c911072206914d1f355156e95826228cea8d',
      sourceStart: 3737,
      sourceEnd: 4304,
      evidence: '孔明緩步登壇，觀瞻方位已定，焚香於爐，注水於盂，仰天暗祝。',
      visualDescription:
        '三层土坛中央有通向坛顶的台阶。蓝灰道衣、长发的孔明在坛顶抬臂，执事分立四周，军士围列于外圈，坛周竖有旗帜。',
    },
    {
      id: 'wind-in-tent',
      imageAsset: '8ad2b717-eb50-404c-9900-516cc67a53d0',
      imageHash: 'd94c85341910a67e5c370fc73afa62548ac3e38aede66f4316b562dd68676b26',
      sourceStart: 5183,
      sourceEnd: 6014,
      evidence: '忽聽風聲響，旗旛轉動。',
      visualDescription:
        '无人帐内近景。左侧铜灯的火焰、红布和右侧浅色帐帘朝同一方向倾动，木桌上放着竹简。',
      displayAfter: {
        introduction: '後人有詩曰：',
        paragraphs: [
          { start: 6027, end: 6075, text: '七星壇上臥龍登，一夜東風江水騰。' },
          { start: 6088, end: 6136, text: '不是孔明施妙計，周郎安得逞才能？' },
        ],
      },
    },
    {
      id: 'zhaoyun-arrow',
      imageAsset: '941e1827-aa61-4962-adeb-6369a467fb3b',
      imageHash: 'ce1932d0dc651358c4008f4062a43500f6bfda835e15825194982fc089a21f66',
      sourceStart: 6936,
      sourceEnd: 7359,
      evidence: '言迄，箭到處，射斷徐盛船上篷索。',
      visualDescription:
        '赵云穿白甲、戴白羽冠，放箭后松开手指，望向追船；蓝袍孔明站在身后。右后方绳索断落、帆布垂下，前景可见桨手和船舷。',
    },
    {
      id: 'orders-ensemble',
      imageAsset: 'c743ca42-f9a9-4ada-ad94-bfcc09cd8ba6',
      imageHash: '53bc3298a02e19f7ecd3a536ed3a368efc89e6af6ef3c805a1f6fb769782e384',
      sourceStart: 10264,
      sourceEnd: 10567,
      evidence: '又喚張飛曰：「翼德可領三千兵渡江，截斷彝陵這條路，去葫蘆谷口埋伏。',
      visualDescription:
        '孔明指向案面，张飞托腮坐在另一侧，关羽站在两人之间偏后；白甲赵云背身走向帐外，左侧另有随员。案上摆着木块、铜炉和竹简。',
    },
    {
      id: 'huanggai-departure',
      imageAsset: 'a7cf7f7f-b014-4a70-8c79-cd52f58b6ca7',
      imageHash: 'f0dde43b8e6292bb078459bf1eb6849786114d79dde3b513e19eee9c437b3f01',
      sourceStart: 13435,
      sourceEnd: 13993,
      evidence: '黃蓋在第三隻火船上，獨披掩心甲，手提利刃',
      visualDescription:
        '白须黄盖穿褐甲、黄褐内衣，站在船上，一手持下垂的刀，另一手指挥。军士俯身捆扎草束与油瓮，船边挂有灯笼，船队尚未燃烧。',
    },
    {
      id: 'caocao-watch',
      imageAsset: '7acccf3b-78ba-4e97-9951-0f9de0065d69',
      imageHash: '11592169a5a84050a52097d97483fd466243a7955421d7872730f981b7fe7465',
      sourceStart: 14000,
      sourceEnd: 14375,
      evidence: '操迎風大笑，自以為得志。',
      visualDescription:
        '曹操着深袍、戴冠，留灰黑胡须，在木栏甲板上昂首背手；身后一名谋士抬手。江面来船尚未起火。',
    },
    {
      id: 'fire-panorama',
      imageAsset: '1132535c-26bc-4091-9870-28e1aa358e33',
      imageHash: 'a3cf3ae81de4c220dcdf17e085dc990d87ba7b1466a07da57269fe6fd01b8fd3',
      sourceStart: 15383,
      sourceEnd: 15974,
      evidence: '曹操回觀岸上營寨，幾處煙火。',
      visualDescription:
        '江面广角图。成排大船及岸上营地燃起烟火，桅杆密集；前景小舟上有舟子回头望向火场，人物身份未作标定。',
      displayAfter: {
        introduction: '正是：',
        paragraphs: [{ start: 15987, end: 16035, text: '火厄盛時遭水厄，棒瘡愈後患金瘡。' }],
      },
    },
    {
      id: 'retreat-column',
      imageAsset: '95601ac3-c747-47f1-a69a-542665f76a87',
      imageHash: 'e2c3682aa503160ab1d8986c21009d7225b87ed47540df7f62c9e782aa5accc1',
      sourceStart: 19063,
      sourceEnd: 19465,
      evidence: '縱馬加鞭，走至五更，回望火光漸遠，操心方定',
      visualDescription:
        '曹操衣袍沾泥，低头骑马走在队列中。前景军士互相搀扶，后方有辎重，队伍沿弯折的泥泞山路行进。',
    },
    {
      id: 'zhangfei-ambush',
      imageAsset: '761dbfea-aaeb-4488-8c74-38c21cd6145f',
      imageHash: '819c4d09a870c14d38a0635d94bc0efc47401c426e6307c3fbd28f85d6183dc3',
      sourceStart: 21033,
      sourceEnd: 21528,
      evidence: '為首乃燕人張翼德，橫矛立馬，大叫：「操賊走那裏去！」',
      visualDescription:
        '浓须张飞穿深甲、红褐衣，骑马居高，长矛横在身前。曹操在右前方回身面对他，亲兵聚在身旁；两队之间可见谷口岩壁与道路。',
    },
    {
      id: 'huarong-encounter',
      imageAsset: '53b3c1af-7fa1-4d44-b78e-700290d86561',
      imageHash: '5bfbee208326df5a891fe80d24a2f311734f13c9351d187a3f9e290c8545e0ac',
      sourceStart: 24263,
      sourceEnd: 24806,
      evidence: '曹操兵敗勢危，到此無路，望將軍以昔日之情為重。',
      visualDescription:
        '曹操在左侧欠身，手靠胸前，抬眼望向右侧关羽。关羽绿袍长须，竖刀肃立，身旁有红棕马。曹军衣装疲敝，关军排列有序，道路仍被挡住。',
    },
  ],
} satisfies PlatePresentationRecipe
