#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
美团商品数据写入器 - 真正的断点续爬版本
记录精确的断档位置，支持从断档位置准确续爬，追加写入原文件
"""

import os
import csv
import json
from datetime import datetime
from typing import Dict, List, Any, Optional, Tuple

# 导入门店指纹识别系统
try:
    import sys
    fingerprint_path = os.path.join(os.path.dirname(__file__), '../小程序采集/win_wechat_mini')
    if fingerprint_path not in sys.path:
        sys.path.insert(0, fingerprint_path)
    from store_fingerprint import get_enhanced_store_key
    ENABLE_STORE_FINGERPRINT = True
except ImportError as e:
    ENABLE_STORE_FINGERPRINT = False
    print(f"⚠️ 门店指纹识别系统未启用: {e}，将使用传统门店名称匹配")


class MeituanGoodsWriterBreakpoint:
    """美团商品数据写入器 - 断点续爬版"""
    
    def __init__(self, base_dir: str = "reports/miniapp"):
        self.base_dir = base_dir
        self.store_name = None
        self.csv_file_path = None
        self.csv_writer = None
        self.csv_file = None
        self.resume_state_file = None
        self.is_resuming = False
        self.resume_state = None
        self.goods_written_count = 0
        
        # 确保目录存在
        os.makedirs(self.base_dir, exist_ok=True)
    
    def begin(self, store_name_or_poi: str, poi_info: Optional[Dict] = None) -> Tuple[bool, Optional[Dict]]:
        """
        开始爬取，检查是否存在断点续爬状态
        
        Args:
            store_name_or_poi: 门店名称或POI信息
            poi_info: 门店POI信息（可选，用于增强识别）
            
        Returns:
            Tuple[bool, Optional[Dict]]: (是否为续爬, 断点状态)
        """
        # 使用门店指纹识别系统（如果可用）
        if ENABLE_STORE_FINGERPRINT and poi_info:
            fingerprint, store_info, display_name = get_enhanced_store_key(poi_info)
            self.store_name = display_name
            self.store_fingerprint = fingerprint
            self.store_info = store_info
            # 使用指纹作为状态文件名（更可靠）
            self.resume_state_file = os.path.join(self.base_dir, f"resume_state_{fingerprint}.json")
            print(f"🔍 门店指纹: {fingerprint} | 显示名: {display_name}")
        else:
            # 传统模式：使用门店名称
            if isinstance(store_name_or_poi, dict):
                self.store_name = store_name_or_poi.get('name', '未知门店')
            else:
                self.store_name = store_name_or_poi
            self.store_fingerprint = None
            self.store_info = {}
            self.resume_state_file = os.path.join(self.base_dir, f"resume_state_{self.store_name}.json")
        
        # 检查是否存在断点续爬状态
        resume_state = self._load_resume_state()
        
        # 如果使用指纹识别，还要检查传统命名的状态文件
        if not resume_state and ENABLE_STORE_FINGERPRINT:
            legacy_state_file = os.path.join(self.base_dir, f"resume_state_{self.store_name}.json")
            if os.path.exists(legacy_state_file):
                print(f"🔄 发现传统命名的断点文件，正在迁移...")
                resume_state = self._load_legacy_state(legacy_state_file)
                
        if resume_state:
            # 验证门店匹配性
            if self._validate_store_match(resume_state):
                print(f"✅ 检测到有效断点续爬状态:")
                print(f"   店铺: {resume_state['store_name']}")
                print(f"   指纹: {resume_state.get('store_fingerprint', '传统模式')}")
                print(f"   断档分类: {resume_state.get('current_category', '未知')}")
                print(f"   断档页码: {resume_state.get('current_page', 0)}")
                print(f"   断档商品索引: {resume_state.get('current_item_index', 0)}")
                print(f"   断档时间: {resume_state.get('last_update_time', '未知')}")
                print(f"   已爬取商品: {resume_state.get('total_goods_count', 0)} 个")
            else:
                print(f"⚠️ 断点状态文件存在但门店不匹配，将开始新的爬取")
                resume_state = None
            
            # 打开现有文件进行追加
            existing_file = resume_state.get('csv_file_path')
            if existing_file and os.path.exists(existing_file):
                self.csv_file_path = existing_file
                print(f"📂 续写文件: {self.csv_file_path}")
            else:
                print("⚠️  断点文件不存在，将创建新文件")
                self._create_new_file()
            
            self.is_resuming = True
            self.resume_state = resume_state
            return True, resume_state
        else:
            print(f"🆕 首次爬取店铺: {self.store_name}")
            self._create_new_file()
            self.is_resuming = False
            return False, None
    
    def _create_new_file(self):
        """创建新的CSV文件"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"miniapp_mt_{self.store_name}_{timestamp}.csv"
        self.csv_file_path = os.path.join(self.base_dir, filename)
        print(f"📁 创建新文件: {self.csv_file_path}")
    
    def _load_resume_state(self) -> Optional[Dict]:
        """加载断点续爬状态"""
        if not os.path.exists(self.resume_state_file):
            return None
        
        try:
            with open(self.resume_state_file, 'r', encoding='utf-8') as f:
                state = json.load(f)
                return state
        except Exception as e:
            print(f"⚠️  读取断点状态失败: {e}")
            return None
    
    def _save_resume_state(self, category: str = "", page: int = 0, item_index: int = 0):
        """保存断点续爬状态"""
        state = {
            "store_name": self.store_name,
            "csv_file_path": self.csv_file_path,
            "current_category": category,
            "current_page": page,
            "current_item_index": item_index,
            "total_goods_count": self.goods_written_count,
            "last_update_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        
        # 添加门店指纹信息（如果可用）
        if hasattr(self, 'store_fingerprint') and self.store_fingerprint:
            state["store_fingerprint"] = self.store_fingerprint
        if hasattr(self, 'store_info') and self.store_info:
            state["store_info"] = self.store_info
        
        try:
            with open(self.resume_state_file, 'w', encoding='utf-8') as f:
                json.dump(state, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"⚠️  保存断点状态失败: {e}")
    
    def _validate_store_match(self, resume_state: Dict) -> bool:
        """验证断点状态是否匹配当前门店"""
        if not resume_state:
            return False
            
        # 如果使用门店指纹，优先进行指纹匹配
        if hasattr(self, 'store_fingerprint') and self.store_fingerprint:
            stored_fingerprint = resume_state.get('store_fingerprint')
            if stored_fingerprint:
                # 指纹匹配（最可靠）
                if stored_fingerprint == self.store_fingerprint:
                    return True
                # 如果指纹不匹配，检查是否是指纹级别降级（如STRONG->MEDIUM）
                if ENABLE_STORE_FINGERPRINT:
                    try:
                        from store_fingerprint import STORE_FINGERPRINT
                        if STORE_FINGERPRINT.is_same_store(stored_fingerprint, self.store_fingerprint):
                            print(f"🔄 检测到门店指纹级别变化: {stored_fingerprint} -> {self.store_fingerprint}")
                            return True
                    except:
                        pass
        
        # 传统名称匹配（兜底）
        stored_name = resume_state.get('store_name', '')
        if stored_name and stored_name == self.store_name:
            return True
            
        return False
    
    def _load_legacy_state(self, legacy_file: str) -> Optional[Dict]:
        """加载传统命名的断点状态文件"""
        try:
            with open(legacy_file, 'r', encoding='utf-8') as f:
                state = json.load(f)
                # 迁移到新的指纹文件（如果使用指纹识别）
                if hasattr(self, 'store_fingerprint') and self.store_fingerprint:
                    # 更新状态文件中的指纹信息
                    state['store_fingerprint'] = self.store_fingerprint
                    if hasattr(self, 'store_info'):
                        state['store_info'] = self.store_info
                    
                    # 保存到新的指纹文件
                    with open(self.resume_state_file, 'w', encoding='utf-8') as new_f:
                        json.dump(state, new_f, ensure_ascii=False, indent=2)
                    
                    # 删除旧文件
                    try:
                        os.remove(legacy_file)
                        print(f"✅ 已迁移断点状态到指纹文件: {os.path.basename(self.resume_state_file)}")
                    except:
                        pass
                
                return state
        except Exception as e:
            print(f"⚠️  读取遗留断点状态失败: {e}")
            return None
    
    def should_skip_to_position(self, category: str, page: int, item_index: int) -> bool:
        """
        判断是否应该跳转到指定位置（断点续爬逻辑）
        
        Returns:
            True: 当前位置在断档位置之前，应该跳过
            False: 已到达或超过断档位置，应该开始爬取
        """
        if not self.is_resuming or not self.resume_state:
            return False
        
        resume_category = self.resume_state.get('current_category', '')
        resume_page = self.resume_state.get('current_page', 0)
        resume_item_index = self.resume_state.get('current_item_index', 0)
        
        # 如果还没到断档的分类，跳过
        if category != resume_category:
            return True
        
        # 在断档分类中，如果页码小于断档页码，跳过
        if page < resume_page:
            return True
        
        # 在断档页码中，如果商品索引小于等于断档索引，跳过
        if page == resume_page and item_index <= resume_item_index:
            return True
        
        # 到达断档位置后的第一个商品，开始正常爬取
        if page == resume_page and item_index == resume_item_index + 1:
            print(f"🎯 到达断档续爬位置: {category} 第{page}页 第{item_index}个商品")
            print("📝 开始续写数据...")
            self._open_csv_file_for_append()
            return False
        
        return False
    
    def _open_csv_file_for_append(self):
        """打开CSV文件进行追加写入"""
        if self.csv_file is None:
            self.csv_file = open(self.csv_file_path, 'a', newline='', encoding='utf-8-sig')
            self.csv_writer = csv.writer(self.csv_file)
            print(f"📂 打开文件进行追加: {self.csv_file_path}")
    
    def _open_csv_file_for_new(self):
        """打开CSV文件进行新建写入"""
        if self.csv_file is None:
            self.csv_file = open(self.csv_file_path, 'w', newline='', encoding='utf-8-sig')
            self.csv_writer = csv.writer(self.csv_file)
            
            # 写入表头
            headers = [
                '美团一级分类', '美团三级分类', '商家分类', '商品名称', '规格名称', 
                '条码', '原价', '售价', '到手价', '第一件价', '月售', '库存', 
                '门店名称', '采集时间'
            ]
            self.csv_writer.writerow(headers)
            print(f"📁 创建新文件并写入表头: {self.csv_file_path}")
    
    def write_goods(self, goods_list: List[Dict[str, Any]], category1: str, category3: str, 
                   store_category: str, page: int = 0) -> int:
        """
        写入商品数据
        
        Returns:
            int: 实际写入的商品数量
        """
        if not goods_list:
            return 0
        
        # 如果是新文件，打开并写入表头
        if not self.is_resuming and self.csv_file is None:
            self._open_csv_file_for_new()
        
        written_count = 0
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        for i, goods in enumerate(goods_list):
            # 断点续爬逻辑：检查是否应该跳过当前商品
            if self.should_skip_to_position(category1, page, i):
                continue
            
            # 确保CSV文件已打开（可能在should_skip_to_position中打开）
            if self.csv_file is None:
                if self.is_resuming:
                    self._open_csv_file_for_append()
                else:
                    self._open_csv_file_for_new()
            
            # 写入商品数据
            row = [
                category1,                          # 美团一级分类
                category3,                          # 美团三级分类  
                store_category,                     # 商家分类
                goods.get('name', ''),              # 商品名称
                goods.get('spec', ''),              # 规格名称
                goods.get('barcode', ''),           # 条码
                goods.get('origin_price', ''),      # 原价
                goods.get('price', ''),             # 售价
                goods.get('activity_price', ''),    # 到手价
                goods.get('first_price', ''),       # 第一件价
                goods.get('month_sold', ''),        # 月售
                goods.get('stock', ''),             # 库存
                self.store_name,                    # 门店名称
                current_time                        # 采集时间
            ]
            
            self.csv_writer.writerow(row)
            written_count += 1
            self.goods_written_count += 1
            
            # 每10个商品保存一次断点状态
            if written_count % 10 == 0:
                self._save_resume_state(category1, page, i)
        
        # 刷新文件缓冲区
        if self.csv_file:
            self.csv_file.flush()
        
        # 保存最新的断点状态
        if written_count > 0:
            last_index = len(goods_list) - 1
            self._save_resume_state(category1, page, last_index)
            
        return written_count
    
    def finish(self):
        """完成爬取，清理资源"""
        if self.csv_file:
            self.csv_file.close()
            self.csv_file = None
            self.csv_writer = None
        
        # 删除断点续爬状态文件（爬取完成）
        if os.path.exists(self.resume_state_file):
            try:
                os.remove(self.resume_state_file)
                print(f"🗑️  删除断点状态文件: {self.resume_state_file}")
            except Exception as e:
                print(f"⚠️  删除断点状态文件失败: {e}")
        
        if self.csv_file_path:
            print(f"✅ 爬取完成，数据已保存到: {self.csv_file_path}")
            print(f"📊 总计爬取商品: {self.goods_written_count} 个")
    
    def update_category_progress(self, category: str, page: int):
        """更新分类爬取进度"""
        self._save_resume_state(category, page, 0)
        print(f"📝 更新进度: {category} 第{page}页")
    
    def get_current_file_path(self) -> Optional[str]:
        """获取当前文件路径"""
        return self.csv_file_path
    
    def get_written_count(self) -> int:
        """获取已写入商品数量"""
        return self.goods_written_count