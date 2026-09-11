"""
簡易菜單驗證服務

提供靜態菜單資料驗證功能，未來可替換為完整菜單模組
"""
from typing import Dict, List, Optional, Any
import logging

from app.exceptions import ValidationError

logger = logging.getLogger(__name__)

# 靜態菜單資料
MENU_DATA = {
    "menus": [
        {
            "menu_Id": 1,
            "menu_Name": "阿明麵食館",
            "menu_Items": [
                {
                    "menu_Item_Id": 101,
                    "menu_Item_Name": "牛肉麵",
                    "category": "主食",
                    "Price": 125
                },
                {
                    "menu_Item_Id": 102,
                    "menu_Item_Name": "陽春麵",
                    "category": "主食", 
                    "Price": 70
                },
                {
                    "menu_Item_Id": 103,
                    "menu_Item_Name": "炸醬麵",
                    "category": "主食",
                    "Price": 110
                },
                {
                    "menu_Item_Id": 104,
                    "menu_Item_Name": "滷蛋",
                    "category": "小菜",
                    "Price": 15
                },
                {
                    "menu_Item_Id": 105,
                    "menu_Item_Name": "滷豆干",
                    "category": "小菜",
                    "Price": 20
                },
                {
                    "menu_Item_Id": 106,
                    "menu_Item_Name": "泡菜",
                    "category": "小菜",
                    "Price": 25
                }
            ]
        },
        {
            "menu_Id": 2,
            "menu_Name": "小華便當店",
            "menu_Items": [
                {
                    "menu_Item_Id": 201,
                    "menu_Item_Name": "雞腿便當",
                    "category": "主食",
                    "Price": 120
                },
                {
                    "menu_Item_Id": 202,
                    "menu_Item_Name": "排骨便當",
                    "category": "主食",
                    "Price": 110
                },
                {
                    "menu_Item_Id": 203,
                    "menu_Item_Name": "魚便當",
                    "category": "主食",
                    "Price": 100
                },
                {
                    "menu_Item_Id": 204,
                    "menu_Item_Name": "可樂",
                    "category": "飲料",
                    "Price": 25
                },
                {
                    "menu_Item_Id": 205,
                    "menu_Item_Name": "雪碧",
                    "category": "飲料",
                    "Price": 25
                },
                {
                    "menu_Item_Id": 206,
                    "menu_Item_Name": "冰紅茶",
                    "category": "飲料",
                    "Price": 30
                }
            ]
        },
        {
            "menu_Id": 3,
            "menu_Name": "清心飲料店",
            "menu_Items": [
                {
                    "menu_Item_Id": 301,
                    "menu_Item_Name": "珍珠奶茶",
                    "category": "飲料",
                    "Price": 50
                },
                {
                    "menu_Item_Id": 302,
                    "menu_Item_Name": "檸檬綠茶",
                    "category": "飲料",
                    "Price": 35
                },
                {
                    "menu_Item_Id": 303,
                    "menu_Item_Name": "冬瓜茶",
                    "category": "飲料",
                    "Price": 30
                },
                {
                    "menu_Item_Id": 304,
                    "menu_Item_Name": "芋頭奶茶",
                    "category": "飲料",
                    "Price": 55
                },
                {
                    "menu_Item_Id": 305,
                    "menu_Item_Name": "多多綠茶",
                    "category": "飲料",
                    "Price": 40
                }
            ]
        },
        {
            "menu_Id": 4,
            "menu_Name": "老王湯麵店",
            "menu_Items": [
                {
                    "menu_Item_Id": 401,
                    "menu_Item_Name": "酸辣湯麵",
                    "category": "主食",
                    "Price": 100
                },
                {
                    "menu_Item_Id": 402,
                    "menu_Item_Name": "餛飩麵",
                    "category": "主食",
                    "Price": 130
                },
                {
                    "menu_Item_Id": 403,
                    "menu_Item_Name": "紫菜蛋花湯",
                    "category": "湯類",
                    "Price": 40
                },
                {
                    "menu_Item_Id": 404,
                    "menu_Item_Name": "酸辣湯",
                    "category": "湯類",
                    "Price": 50
                },
                {
                    "menu_Item_Id": 405,
                    "menu_Item_Name": "海帶絲",
                    "category": "小菜",
                    "Price": 30
                },
                {
                    "menu_Item_Id": 406,
                    "menu_Item_Name": "小黃瓜",
                    "category": "小菜",
                    "Price": 25
                }
            ]
        }
    ]
}


class MenuValidationService:
    """菜單驗證服務"""

    def __init__(self):
        # 建立快速查詢索引
        self._menu_index: Dict[int, Dict] = {}
        self._item_index: Dict[int, Dict] = {}
        self._build_indexes()

    def _build_indexes(self):
        """建立菜單和餐點的快速查詢索引"""
        for menu in MENU_DATA["menus"]:
            menu_id = menu["menu_Id"]
            self._menu_index[menu_id] = {
                "menu_Name": menu["menu_Name"],
                "items": {}
            }
            
            for item in menu["menu_Items"]:
                item_id = item["menu_Item_Id"]
                item_data = {
                    "menu_Id": menu_id,
                    "menu_Item_Name": item["menu_Item_Name"],
                    "Price": item["Price"],
                    "category": item["category"]
                }
                
                # 菜單內餐點索引
                self._menu_index[menu_id]["items"][item_id] = item_data
                
                # 全域餐點索引
                self._item_index[item_id] = item_data

    def validate_menu_exists(self, menu_id: int) -> bool:
        """驗證菜單是否存在"""
        return menu_id in self._menu_index

    def validate_menu_item_exists(self, menu_id: int, menu_item_id: int) -> bool:
        """驗證餐點是否存在於指定菜單中"""
        if menu_id not in self._menu_index:
            return False
        return menu_item_id in self._menu_index[menu_id]["items"]

    def get_menu_item_info(self, menu_id: int, menu_item_id: int) -> Optional[Dict]:
        """取得餐點資訊"""
        if not self.validate_menu_item_exists(menu_id, menu_item_id):
            return None
        return self._menu_index[menu_id]["items"][menu_item_id]

    def validate_order_item(
        self, 
        menu_id: int, 
        menu_item_id: int, 
        menu_item_name: str, 
        unit_price: int
    ) -> None:
        """
        驗證單個訂單項目的完整性
        
        Args:
            menu_id: 菜單ID
            menu_item_id: 餐點ID
            menu_item_name: 餐點名稱
            unit_price: 單價
            
        Raises:
            ValidationError: 驗證失敗時拋出具體錯誤
        """
        # 1. 驗證菜單ID存在
        if not self.validate_menu_exists(menu_id):
            raise ValidationError(
                f"無效的菜單ID: {menu_id}，該菜單不存在"
            )

        # 2. 驗證餐點ID是否存在於該菜單中
        if not self.validate_menu_item_exists(menu_id, menu_item_id):
            # 檢查餐點是否存在於其他菜單
            if menu_item_id in self._item_index:
                correct_menu_id = self._item_index[menu_item_id]["menu_Id"]
                menu_name = self._menu_index[correct_menu_id]["menu_Name"]
                raise ValidationError(
                    f"餐點ID {menu_item_id} 不屬於菜單ID {menu_id}，"
                    f"該餐點屬於菜單ID {correct_menu_id}（{menu_name}）"
                )
            else:
                raise ValidationError(
                    f"無效的餐點ID: {menu_item_id}，該餐點不存在"
                )

        # 3. 取得正確的餐點資訊
        item_info = self.get_menu_item_info(menu_id, menu_item_id)
        
        # 4. 驗證餐點名稱
        if item_info["menu_Item_Name"] != menu_item_name:
            raise ValidationError(
                f"餐點名稱不符：餐點ID {menu_item_id} 的正確名稱為 '{item_info['menu_Item_Name']}'，"
                f"但收到 '{menu_item_name}'"
            )

        # 5. 驗證價格
        if item_info["Price"] != unit_price:
            raise ValidationError(
                f"餐點價格不符：餐點 '{menu_item_name}' 的正確價格為 {item_info['Price']} 元，"
                f"但收到 {unit_price} 元"
            )

        logger.info(f"✅ 餐點驗證通過：{menu_item_name} (ID: {menu_item_id}, 價格: {unit_price})")

    def get_menu_name(self, menu_id: int) -> Optional[str]:
        """取得菜單名稱"""
        if menu_id in self._menu_index:
            return self._menu_index[menu_id]["menu_Name"]
        return None


# 全域菜單服務實例
menu_service = MenuValidationService()