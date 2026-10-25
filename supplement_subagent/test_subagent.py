#!/usr/bin/env python3
"""
NutriRecSubAgent系统测试文件
使用真实知识库数据测试多专家并发咨询功能
支持动态API配置
"""

import asyncio
import json
import logging
import os
from datetime import datetime
from subagent_system import get_subagent_system

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

class SubAgentTester:
    """SubAgent系统测试器"""
    
    def __init__(self):
        self.system = get_subagent_system()
        self.api_config = self._setup_api_config()
        
    def _setup_api_config(self) -> dict:
        """设置API配置"""
        print("🔧 API配置设置")
        print("=" * 50)
        
        # 尝试从环境变量读取
        deepseek_key = os.getenv('DEEPSEEK_API_KEY')
        openai_key = os.getenv('OPENAI_API_KEY')
        claude_key = os.getenv('CLAUDE_API_KEY') or os.getenv('ANTHROPIC_API_KEY')
        
        # 显示可用的配置
        available_providers = []
        if deepseek_key:
            available_providers.append("deepseek")
        if openai_key:
            available_providers.append("openai")
        if claude_key:
            available_providers.append("claude")
            
        if not available_providers:
            print("⚠️ 未检测到环境变量中的API密钥")
            print("请手动输入API配置:")
            
            provider = input("请选择API提供商 (openai/deepseek/claude/grok/gemini): ").strip().lower()
            api_key = input("请输入API密钥: ").strip()
            model_name = input(f"请输入模型名称 (默认根据提供商自动选择): ").strip()
            
            # 设置默认模型
            if not model_name:
                default_models = {
                    'openai': 'gpt-4o-mini',
                    'deepseek': 'deepseek-chat',
                    'claude': 'claude-3-5-sonnet-20241022',
                    'grok': 'grok-beta',
                    'gemini': 'gemini-1.5-pro'
                }
                model_name = default_models.get(provider, 'gpt-4o-mini')
            
            return {
                'provider': provider,
                'model_name': model_name,
                'api_key': api_key,
                'base_url': None,
                'max_tokens': 8000,
                'temperature': 0.7,
                'timeout': 60,
                'max_workers': 6
            }
        else:
            print(f"✅ 检测到可用的API提供商: {', '.join(available_providers)}")
            
            # 让用户选择
            if len(available_providers) == 1:
                provider = available_providers[0]
                print(f"🎯 自动选择: {provider}")
            else:
                print("请选择要使用的API提供商:")
                for i, p in enumerate(available_providers, 1):
                    print(f"{i}. {p}")
                
                try:
                    choice = int(input("请输入选择 (数字): ").strip()) - 1
                    provider = available_providers[choice]
                except (ValueError, IndexError):
                    provider = available_providers[0]
                    print(f"无效选择，自动选择: {provider}")
            
            # 获取对应的API密钥
            if provider == 'deepseek':
                api_key = deepseek_key
                model_name = 'deepseek-chat'
                base_url = 'https://api.deepseek.com'
            elif provider == 'openai':
                api_key = openai_key
                model_name = 'gpt-4o-mini'
                base_url = None
            elif provider == 'claude':
                api_key = claude_key
                model_name = 'claude-3-5-sonnet-20241022'
                base_url = None
            
            print(f"🔧 使用配置: {provider} / {model_name}")
            
            return {
                'provider': provider,
                'model_name': model_name,
                'api_key': api_key,
                'base_url': base_url,
                'max_tokens': 8000,
                'temperature': 0.7,
                'timeout': 60,
                'max_workers': 6
            }
    
    def test_api_connection(self):
        """测试API连接"""
        print("\n🔧 测试API连接...")
        return self.system.test_api_connection(
            provider=self.api_config['provider'],
            model_name=self.api_config['model_name'],
            api_key=self.api_config['api_key'],
            base_url=self.api_config['base_url']
        )
        
    def create_test_case_1(self) -> str:
        """测试案例1：失眠和疲劳问题"""
        return """
用户问题：我最近总是失眠，白天很疲劳，想了解一下有什么好的保健品可以改善睡眠质量？

用户信息：
- 年龄：30岁
- 性别：女
- 健康状况：失眠、疲劳、工作压力大
- 偏好：喜欢天然产品，不喜欢化学合成品
- 过敏史：无已知过敏
- 正在服用药物：无

相关保健品信息：
【产品1】
- 分类：儿童营养补剂
- 商品名：童年故事复合磷脂酰丝氨酸凝胶糖果
- 链接：https://shop137071643.m.youzan.com/v2/goods/1yegdyu69ofur4j
- 商品简介/功效：产品名称：童年故事倍启智复合磷脂酰丝氨酸凝胶糖果。功效：产品类型本品是一款专为儿童设计的营养补充品，具有健脑益智，帮助儿童舒缓情绪，原装进口，成分安全，采用凝胶糖果形式，口感佳，儿童更易接受。
- 商品用量用法：建议用量：每日1-2粒，建议用法：直接咀嚼食用
- 商品成分：成分：每粒含100mg磷脂酰丝氨酸（PS）和50mg DHA
- 商品忌口/限制：注意事项：本品添加新资源食品成分：DHA藻油、磷脂酰丝氨酸（PS）。推荐食用量限制：DHA藻油：≤300毫克/天（以纯DHA计）、磷脂酰丝氨酸：≤600毫克/天。禁忌人群：不适用于婴幼儿
- 商品标签：大脑营养补充、学习期营养、学生党必备、备考加油站、聪明宝宝的小零食、含PS+DHA双效成分、磷脂酰丝氨酸配方、Omega-3营养补充

【产品2】
- 分类：科学备孕
- 商品名：爱乐维玛咖锌淫羊藿胶囊
- 链接：https://shop137071643.m.youzan.com/v2/goods/36fwvh64l2v4w
- 商品简介/功效：产品名称：爱乐维玛咖锌淫羊藿胶囊。功效：本品以玛咖粉、锌酵母、淫羊藿提取物、黄精提取物为主要原料制成的保健食品，经动物功能试验证明，具有缓解体力疲劳的保健功能。
- 商品用量用法：建议用量：每日2次，每次2粒，建议用法：温水送服
- 商品成分：成分：每100g含：锌408mg，每粒胶囊含玛咖粉200mg
- 商品忌口/限制：注意事项：本品不能代替药物；不适宜人群：少年儿童、孕妇、乳母
- 商品标签：缓解疲劳、男性健康、玛咖精华、锌元素补充、淫羊藿配方、体力恢复、精力提升、成人营养

【产品3】
- 分类：睡眠改善
- 商品名：好眠褪黑素软胶囊
- 链接：https://shop137071643.m.youzan.com/v2/goods/2fg7ck69l8v2w
- 商品简介/功效：产品名称：好眠褪黑素软胶囊。功效：本品以褪黑素为主要原料制成的保健食品，经动物功能试验证明，具有改善睡眠的保健功能。每粒含褪黑素3mg，有助于缩短入睡时间，改善睡眠质量。
- 商品用量用法：建议用量：每日1粒，建议用法：睡前30分钟温水送服
- 商品成分：成分：每粒含褪黑素3mg，辅料：大豆油、明胶、甘油、水
- 商品忌口/限制：注意事项：本品不能代替药物；不适宜人群：少年儿童、孕妇、乳母；服用后可能出现困倦，请避免驾驶汽车或操作机械
- 商品标签：改善睡眠、褪黑素配方、快速入睡、睡眠质量、天然助眠、成人保健、夜间修复

相关合作门诊信息：
【门诊1】
- 门诊名称：番禺万博门诊部
- 门诊地址：广州市番禺区兴南大道421号万博翠湖花园商业街102号
- 门诊电话：020-31141662
- 营业时间：周一至周日 09:00-18:30
- 核心服务：全科医疗、健康体检、慢病管理、疫苗接种、中医理疗
- 停车信息：提供免费停车位，商业街地下停车场

【门诊2】
- 门诊名称：天河珠江新城门诊部
- 门诊地址：广州市天河区珠江新城华夏路8号合景国际金融广场28楼
- 门诊电话：020-85558866转801
- 营业时间：周一至周六 08:30-18:00，周日 09:00-17:00
- 核心服务：高端体检、营养咨询、睡眠门诊、心理健康、医美服务
- 停车信息：大厦地下停车场，前台可协助办理免费停车券（3小时内）
        """

    def create_test_case_2(self) -> str:
        """测试案例2：儿童营养问题"""
        return """
用户问题：我家孩子3岁了，最近挑食很严重，担心营养不良影响发育，有什么适合的营养补充剂推荐吗？

用户信息：
- 孩子年龄：3岁
- 性别：男
- 健康状况：挑食、体重偏轻、容易感冒
- 饮食习惯：不爱吃蔬菜，只喜欢吃肉和甜食
- 过敏史：无已知过敏
- 发育情况：身高体重均在正常范围下限

相关保健品信息：
【产品1】
- 分类：儿童营养补剂
- 商品名：童年故事锌牡蛎橙复合饮液
- 链接：https://shop137071643.m.youzan.com/v2/goods/3fu9wb64l1v8x
- 商品简介/功效：产品名称：童年故事锌牡蛎橙复合饮液。功效：本品以锌酵母、牡蛎肽、维生素C为主要原料制成的营养补充品，有助于儿童生长发育，增强免疫力，改善食欲。采用天然橙味，口感佳，儿童易接受。
- 商品用量用法：建议用量：每日0.5ml，建议用法：直接饮用或加入温水中服用
- 商品成分：成分：每0.5ml含锌5mg、牡蛎肽100mg、维生素C30mg
- 商品忌口/限制：注意事项：本品不能代替药物；适用年龄：1岁以上儿童；请勿超量服用
- 商品标签：儿童补锌、挑食改善、生长发育缓慢、免疫力低下、食欲不振、锌缺乏、牡蛎精华、维C增强

【产品2】
- 分类：儿童营养补剂
- 商品名：童年故事维生素D3片
- 链接：https://shop137071643.m.youzan.com/v2/goods/2og8vk69l7v9d
- 商品简介/功效：产品名称：童年故事维生素D3片。功效：本品以维生素D3为主要原料制成的营养补充品，有助于钙的吸收利用，促进骨骼和牙齿的发育，维持免疫系统正常功能。
- 商品用量用法：建议用量：每日1片，建议用法：餐后温水送服
- 商品成分：成分：每片含维生素D3 400IU（10微克）
- 商品忌口/限制：注意事项：本品不能代替药物；适用年龄：6个月以上儿童；请勿超量服用，过量可能导致高钙血症
- 商品标签：儿童维D、长高必备、钙吸收、骨骼发育、牙齿健康、免疫支持、维生素D缺乏

相关合作门诊信息：
【门诊1】
- 门诊名称：儿童康复中心（天河分院）
- 门诊地址：广州市天河区金穗路28号天河科技园A座3楼
- 门诊电话：020-89811485分机206
- 营业时间：周一至周五 08:30-17:30，周六 09:00-16:00
- 核心服务：儿童生长发育评估、营养咨询、行为干预、康复训练、家长指导
- 停车信息：科技园内部停车场，就诊可申请2小时免费停车券

【门诊2】
- 门诊名称：丽晶门诊部
- 门诊地址：广州市天河区天河北路183号大都会广场6楼
- 门诊电话：020-87568899
- 营业时间：周一至周日 08:00-20:00
- 核心服务：儿科门诊、儿童保健、疫苗接种、营养门诊、发育评估
- 停车信息：大都会广场地下停车场，门诊可提供4小时免费停车券
        """

    def create_test_case_3(self) -> str:
        """测试案例3：男性健康问题"""
        return """
用户问题：我今年35岁，最近工作压力大，感觉体力下降，精力不足，想了解一些适合男性的营养保健品？

用户信息：
- 年龄：35岁
- 性别：男
- 健康状况：体力下降、精力不足、工作压力大、睡眠质量差
- 生活习惯：经常熬夜、饮食不规律、缺乏运动
- 过敏史：无已知过敏
- 正在服用药物：偶尔服用维生素B族

相关保健品信息：
【产品1】
- 分类：科学备孕
- 商品名：爱乐维玛咖锌淫羊藿胶囊
- 链接：https://shop137071643.m.youzan.com/v2/goods/36fwvh64l2v4w
- 商品简介/功效：产品名称：爱乐维玛咖锌淫羊藿胶囊。功效：本品以玛咖粉、锌酵母、淫羊藿提取物、黄精提取物为主要原料制成的保健食品，经动物功能试验证明，具有缓解体力疲劳的保健功能。
- 商品用量用法：建议用量：每日2次，每次2粒，建议用法：温水送服
- 商品成分：成分：每100g含：锌408mg，每粒胶囊含玛咖粉200mg
- 商品忌口/限制：注意事项：本品不能代替药物；不适宜人群：少年儿童、孕妇、乳母
- 商品标签：缓解疲劳、男性健康、玛咖精华、锌元素补充、淫羊藿配方、体力恢复、精力提升、成人营养

【产品2】
- 分类：成人营养
- 商品名：深海鱼油软胶囊
- 链接：https://shop137071643.m.youzan.com/v2/goods/2xg8vk69l5v2d
- 商品简介/功效：产品名称：深海鱼油软胶囊。功效：本品以深海鱼油为主要原料，富含EPA和DHA，有助于维护心血管健康，改善血脂，支持大脑功能，抗炎抗氧化。
- 商品用量用法：建议用量：每日2粒，建议用法：餐后温水送服
- 商品成分：成分：每粒含EPA 180mg，DHA 120mg
- 商品忌口/限制：注意事项：本品不能代替药物；出血性疾病患者慎用；正在服用抗凝药物者请咨询医生
- 商品标签：心血管健康、血脂调节、大脑营养、Omega-3、深海提取、抗炎抗氧化、EPA-DHA配比

相关合作门诊信息：
【门诊1】
- 门诊名称：男性健康中心
- 门诊地址：广州市越秀区建设六马路33号宜安广场15楼
- 门诊电话：020-83821888转302
- 营业时间：周一至周六 09:00-18:00
- 核心服务：男性体检、性功能评估、前列腺健康、内分泌调理、营养指导
- 停车信息：宜安广场地下停车场，就诊凭票可享受3小时优惠停车

【门诊2】
- 门诊名称：番禺万博门诊部
- 门诊地址：广州市番禺区兴南大道421号万博翠湖花园商业街102号
- 门诊电话：020-31141662
- 营业时间：周一至周日 09:00-18:30
- 核心服务：全科医疗、健康体检、慢病管理、疫苗接种、中医理疗
- 停车信息：提供免费停车位，商业街地下停车场
        """

    async def run_test_case(self, case_name: str, test_input: str):
        """运行单个测试案例"""
        
        print(f"\n{'='*60}")
        print(f"🧪 开始测试: {case_name}")
        print(f"{'='*60}")
        
        start_time = datetime.now()
        
        try:
            result = await self.system.process_consultation(
                user_input=test_input,
                **self.api_config  # 解包API配置参数
            )
            
            end_time = datetime.now()
            duration = (end_time - start_time).total_seconds()
            
            print(f"📊 测试结果: {result['status']}")
            print(f"⏱️ 总处理时间: {duration:.2f}s")
            
            if result["status"] == "success":
                print(f"👥 专家数量: {len(result['expert_results'])}")
                
                # 显示各专家的处理时间
                print("\n📋 各专家处理时间:")
                for expert in result['expert_results']:
                    print(f"  - {expert['agent_type']}: {expert['processing_time']:.2f}s")
                
                print(f"\n🎯 最终建议预览:")
                final_rec = result['final_recommendation']
                preview = final_rec #[:500] + "..." if len(final_rec) > 500 else final_rec
                print(preview)
                
                # 保存完整结果到文件
                # 确保test_result目录存在
                os.makedirs("./test_result", exist_ok=True)
                output_file = f"./test_result/test_result_{case_name.replace(' ', '_').lower()}_{start_time.strftime('%Y%m%d_%H%M%S')}.json"
                with open(output_file, 'w', encoding='utf-8') as f:
                    json.dump(result, f, ensure_ascii=False, indent=2)
                print(f"\n💾 完整结果已保存到: {output_file}")
                
            else:
                print(f"❌ 错误: {result.get('message', '未知错误')}")
                
        except Exception as e:
            print(f"❌ 测试异常: {str(e)}")
            
        print(f"{'='*60}")

    async def run_all_tests(self):
        """运行所有测试案例"""
        print("🚀 开始SubAgent系统全面测试")
        print(f"测试时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
        test_cases = [
            ("失眠疲劳案例", self.create_test_case_1()),
            ("儿童营养案例", self.create_test_case_2()),
            ("男性健康案例", self.create_test_case_3())
        ]
        
        for case_name, test_input in test_cases:
            await self.run_test_case(case_name, test_input)
            
        print(f"\n✅ 所有测试完成！")

    async def run_single_test(self, test_number: int):
        """运行单个测试案例"""
        test_cases = {
            1: ("失眠疲劳案例", self.create_test_case_1()),
            2: ("儿童营养案例", self.create_test_case_2()),
            3: ("男性健康案例", self.create_test_case_3())
        }
        
        if test_number in test_cases:
            case_name, test_input = test_cases[test_number]
            await self.run_test_case(case_name, test_input)
        else:
            print(f"❌ 无效的测试编号: {test_number}")
            print("可用的测试编号: 1(失眠疲劳), 2(儿童营养), 3(男性健康)")

async def main():
    """主函数"""
    print("NutriRecSubAgent系统测试工具")
    print("支持多种AI模型: OpenAI, DeepSeek, Claude, Grok, Gemini")
    print("=" * 60)
    
    try:
        tester = SubAgentTester()
        
        print("\n测试选项:")
        print("0. 测试API连接")
        print("1. 运行所有测试案例")
        print("2. 运行失眠疲劳案例")
        print("3. 运行儿童营养案例") 
        print("4. 运行男性健康案例")
        
        choice = input("\n请选择测试选项 (0-4): ").strip()
        
        if choice == "0":
            tester.test_api_connection()
        elif choice == "1":
            await tester.run_all_tests()
        elif choice == "2":
            await tester.run_single_test(1)
        elif choice == "3":
            await tester.run_single_test(2)
        elif choice == "4":
            await tester.run_single_test(3)
        else:
            print("无效选择，运行所有测试...")
            await tester.run_all_tests()
            
    except KeyboardInterrupt:
        print("\n\n 测试被用户中断")
    except Exception as e:
        print(f"\n❌ 测试过程中发生错误: {str(e)}")

if __name__ == "__main__":
    asyncio.run(main()) 