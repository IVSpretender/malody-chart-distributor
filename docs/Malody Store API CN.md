>如要提供其他语种翻译，请使用 pull request
# Malody Store API
**Version: 202310**
**最后修订: 2023/10/10**

## 共识

### 请求方法
1. 客户端所有请求都会在QueryString中带有**uid**，**api**，**key**3个参数，其中uid为当前请求用户id。api为客户端的API兼容版本，格式为6位数字，比如202103，不同的API版本，客户端在返回值处理，传参内容方面可能有差异。需要服务器关注并处理。
**key**字段是主服务器签发的认证字段，用于证明uid没有被篡改。私服服务器可以选择对key字段进行校验，参见example。

2. 所有返回值都是**json**类型，其中，当返回类型是列表对象时，返回结构相同部分如下：
    ```json
    {
      "code": 0,
      "hasMore": true,
      "next": 0,
      "data": []
    }
    ```
    其中，**hasMore**表示是否可以继续翻页，**next**表示下一页的起点，客户端请求下一页时，会将next值通过from参数传回给服务器。后续不再赘述此定义
### 模式定义
* Key = 0
* Catch = 3
* Pad = 4
* Taiko = 5
* Ring = 6
* Slide = 7
* Live = 8
* Cube = 9

### 平台定义
* Windows = 0
* MacOS = 1
* Tablet = 2
* iPhone = 3
* Android = 4
* iPad = 5

## 基础信息
### 服务器信息（202108添加）
**用途**：当客户端输入服务器地址后，客户端立刻发起服务器信息查询，当服务器返回版本兼容客户端API版本时，服务器地址才可使用。

**API**：GET /api/store/info

**传参**
无

**返回结构**
```json
{
  "code": 0,
  "api": 202108,
  "min": 202103,
  "welcome": ""
}
```

其中：
* **api**：服务器API版本
* **min**：服务器支持的最低客户端API版本
* **welcome**：欢迎词，客户端验证成功后展示，可选

## 谱面商店
### 歌曲列表（202103添加）
**用途**：获取商城指定查询条件下的谱面列表

**API**：GET ​/api​/store​/list

**传参**
| 参数 | 类型 | 含义 | 默认值
---- | ---- | ---- | ----
word|string|搜索关键词|Empty
org|int|是否返回原始标题|0
mode|int|返回指定模式谱面,定义参见**模式定义**|-1
lvge|int|返回level大于于这个值的谱面|0
lvle|int|返回level小于这个值的谱面|0
beta|int|返回非stable谱面|0
from|int|翻页起点|0

**返回结构**
```json
{
  "code": 0,
  "hasMore": true,
  "next": 0,
  "data": [
    {
      "sid": 0,
      "cover": "string",
      "length": 0,
      "bpm": 0,
      "title": "string",
      "artist": "string",
      "mode": 0,
      "time": 0
    }
  ]
}
```
其中：
* **sid**：song id，唯一标识
* **cover**: 完整的封面url
* **length**：歌曲长度，单位秒
* **bpm**：歌曲bpm，浮点型
* **mode**：歌曲所包含的谱面类型bitmask值，例如歌曲同时包含key和catch两个模式的谱面，bitmask值为(1 << 0) | (1 << 3) = 9
* **time**: 歌曲最后更新时间

### 推荐列表（202103添加）
**用途**：获取当前正在推广的谱面，将显示在客户端Promotion栏里

**API**：GET ​​/api​/store​/promote

**传参**
| 参数 | 类型 | 含义 | 默认值
---- | ---- | ---- | ----
org|int|是否返回原始标题|0
mode|int|返回指定模式谱面,定义参见**模式定义**|-1
from|int|翻页起点|0

**返回结构**
参见**歌曲列表**的返回结构

### 好友最近更新列表（202310添加）
**用途**：获取好友的最新更新内容，将显示在客户端Friends栏里

**API**：GET ​​/api​/store​/friend

**传参**
| 参数 | 类型 | 含义 | 默认值
---- | ---- | ---- | ----
org|int|是否返回原始标题|0
from|int|翻页起点|0

**返回结构**
参见**歌曲列表**的返回结构

### 谱面列表（202103添加）
**用途**：获取指定歌曲下所有谱面

**API**：GET ​​/api​/store​/charts

**传参**
| 参数 | 类型 | 含义 | 默认值
---- | ---- | ---- | ----
sid|int|song id|必填
beta|int|返回非stable谱面|0
mode|int|返回指定模式谱面,定义参见**模式定义**|-1
from|int|翻页起点|0
promote|int|请求来自推荐列表|0, **202206添加**

**返回结构**
```json
{
  "code": 0,
  "hasMore": true,
  "next": 0,
  "data": [
    {
      "cid": 0,
      "uid": 0,
      "creator": "string",
      "version": "string",
      "level": 0,
      "length": 0,
      "type": 0,
      "size": 0,
      "mode": 0
    }
  ]
}
```
其中：
* **cid**：chart id
* **uid**：作者uid
* **creator**：作者用户名
* **version**：谱面难度名，比如4K Easy
* **level**：谱面难度值
* **length**：谱面游玩长度，单位：秒
* **type**：谱面状态，2代表Stable，1代表Beta，0代表Alpha
* **size**：谱面下载大小，单位：字节
* **mode**：模式谱面,定义参见**模式定义**
 

### 谱面查询（202103添加）
**用途**：当客户端输入s(\d+)或c(\d+)内容时，会自动提取数字部分，作为sid和cid调用此接口进行查询

**API**：GET ​​/api​/store​/query

**传参**
| 参数 | 类型 | 含义 | 默认值
---- | ---- | ---- | ----
sid|int|song id|和cid二选一必填
cid|int|chart id|和sid二选一必填
org|int|是否返回原始标题|0

**返回结构**
客户端会将结果显示在歌曲列表中，所以虽然结果通常只有一项，但仍然复用**歌曲列表**的返回结构

### 谱面下载（202103添加）
**用途**：获取指定谱面的下载地址

**API**：GET ​​/api​/store​/download

**传参**
| 参数 | 类型 | 含义 | 默认值
---- | ---- | ---- | ----
cid|int|chart id|必填

**返回结构**
```json
{
  "code": 0,
  "items": [
    {
      "name": "string",
      "hash": "string",
      "file": "string"
    }
  ],
  "sid": 0,
  "cid": 0
}
```
其中：
* **code**：cid对应谱面不存在时返回-2，其他情况保持0
* **items.name**: 文件名
* **items.hash**: 文件md5值
* **items.file**: 文件的下载地址url

## 活动分区
### 分区列表（202103添加）
**用途**：获取所有活动列表

**API**：GET ​​/api​/store​/events

**传参**
| 参数 | 类型 | 含义 | 默认值
---- | ---- | ---- | ----
active|int|返回当前有效的活动|1
from|int|翻页起点|0

**返回结构**
```json
{
  "code": 0,
  "hasMore": true,
  "next": 0,
  "data": [
    {
      "eid": 0,
      "name": "string",
      "sponsor":"string",
      "start": "string",
      "end": "string",
      "active": true,
      "cover": "string",
    }
  ]
}
```
其中：
* **eid**：event id
* **name**：活动标题
* **sponsor**：活动发起人，歌单作者等
* **start**：活动开始时间，格式为yyyy-mm-dd
* **end**：活动结束时间，格式为yyyy-mm-dd
* **cover**：活动展示的封面
* **active**：活动是否有效

### 活动谱面列表（202103添加）
**用途**：获取指定活动下所有谱面

**API**：GET ​​/api​/store​/event

**传参**
| 参数 | 类型 | 含义 | 默认值
---- | ---- | ---- | ----
eid|int|event id|必填
org|int|是否返回原始标题|0
from|int|翻页起点|0

**返回结构**
```json
{
  "code": 0,
  "hasMore": true,
  "next": 0,
  "data": [
    {
      "sid": 0,
      "cid": 0,
      "uid": 0,
      "creator": "string",
      "title": "string",
      "artist": "string",
      "version": "string",
      "level": 0,
      "length": 0,
      "type": 0,
      "cover": "string",
      "time": 0,
      "mode": 0
    }
  ]
}
```
其中：
* **cid**：chart id
* **uid**：作者uid
* **creator**：作者用户名
* **version**：谱面难度名，比如4K Easy
* **level**：谱面难度值，数字
* **length**：谱面游玩长度，单位：秒
* **type**：谱面状态，2代表Stable，1代表Beta，0代表Alpha
* **mode**：模式谱面,定义参见**模式定义**

## 谱面上传
### 综述
Malody的游戏社区和谱面存储分离，官方维护社区部分，为全球玩家提供相同的排行榜和交流平台。为了实现这个目标，谱面上传为了两部分：
1. 谱面登记部分：客户端向**主服务器**请求，创建谱面页，上传基本信息，获取谱面sid,cid
2. 文件上传部分：客户端使用主服务器返回的谱面cid，向**Store服务器**请求上传目的地，上传参数，然后进行文件上传

这样，纵使玩家从多个Store服务下载谱面，最终只要谱面的md5一样，在主服务器看来都是同一份谱面，提供同一个榜单

上传部分为了更好的兼顾上传文件的灵活性和兼容不同文件存储提供商的上传API，将上传一份谱面分为三个阶段：
1. 客户端收集所有需要上传的文件清单，请求服务器获得上传信息，其中包括上传服务器的地址，上传时携带的额外参数
2. 客户端根据上传信息，将文件分别以**multipart/form-data**形式上传到指定服务器
3. 全部文件上传完成后，客户端再次收集文件信息，发送到服务器，确认上传完成

其中步骤2，处于节省流量考虑，mc文件会被压缩为zip再上传，服务器将会收到和mc同名的zip文件

### 获取签名（202103添加）
**用途**：对应上传阶段1

**API**：POST ​​/api​/store​/upload/sign

**传参**
| 参数 | 类型 | 含义 | 默认值
---- | ---- | ---- | ----
sid|int|song id|必填
cid|int|chart id|必填
name|string|所有待文件名，以逗号连接|Empty
hash|string|所有待文件md5，以逗号连接|Empty

**返回结构**
```json
{
  "code": 0,
  "errorIndex": -1,
  "errorMsg": "string",
  "host": "string",
  "meta": [
    {
      "post body key": "post body value"
    }
  ]
}
```
其中：
* **errorIndex**：当服务器认为待上传文件有问题时，返回出问题的文件序号，默认值-1表示没有问题
* **errorMsg**：出错的原因文字描述
* **host**：上传的目标服务器地址
* **meta**：需要添加到form-data的字段key-value对

### 上传确认（202103添加）
**用途**：对应上传阶段3

**API**：POST ​​/api​/store​/upload/finish

**传参**
| 参数 | 类型 | 含义 | 默认值
---- | ---- | ---- | ----
sid|int|song id|必填
cid|int|chart id|必填
name|string|所有待文件名，以逗号连接|Empty
hash|string|所有待文件md5，以逗号连接|Empty
size|int|总文件大小|0
main|string|谱面主文件的md5|Empty
title|string|歌曲标题|**202208添加**
artit|string|歌曲艺术家|**202208添加**
orgt|string|歌曲标题的原文|**202208添加**
orga|string|歌曲艺术家的原文|**202208添加**
version|string|谱面版本|**202208添加**
mode|int|定义参见**模式定义**|**202208添加**
length|int|谱面游玩长度|**202208添加**
bpm|float|谱面主要bpm|**202208添加**

**返回结构**
```json
{
  "code": 0
}
```
* **code**：-1代表name和hash按逗号拆分后长度不相等。-2代表cid对应谱面不存在。

### 延伸讨论
虽然API中规定了服务器同时提供上传和下载两种能力。但实际上也可以只提供下载一项服务。即，服务器的谱面都是由服务器维护者通过自己的渠道获取和保存的。
而这种情况下，谱面的sid，cid无法与官网对应，官服也大概率无法提供排名服务（如果谱面md5相同，虽然cid不同，官服还是可以关联到正确cid）。

## 皮肤
### 皮肤列表（202112添加）
**用途**：获取当前可用的皮肤列表

**API**：GET ​​/api/Skin/list

**传参**
| 参数 | 类型 | 含义 | 默认值
---- | ---- | ---- | ----
plat|int|请求的平台,定义参见**平台定义**|0
mode|int|返回指定模式皮肤,定义参见**模式定义**|-1
word|string|搜索关键字|
from|int|翻页起点|0
v|int|客户端版本|0

**返回结构**
```json
{
  "code": 0,
  "hasMore": true,
  "next": 0,
  "data": [
    {
      "id": 0,
      "uid": 0,
      "creator": "string",
      "name": "string",
      "cover": "string",
      "preview": "string",
      "hot": 0,
      "mode": 0,
      "time": 0
    }
  ]
}
```
其中：
* **uid**：作者uid
* **creator**：作者用户名
* **name**：皮肤名称
* **cover**：皮肤封面的url
* **preview**：皮肤预览图的url，如果有多个预览图，使用|分割
* **hot**：皮肤热度，含义可以自定义
* **time**：皮肤更新时间，unix time
* **mode**：模式谱面,定义参见**模式定义**

### 皮肤下载（202112添加）
**用途**：获得指定皮肤下载地址

**API**：POST ​​/api/skin/buy

**传参**
| 参数 | 类型 | 含义 | 默认值
---- | ---- | ---- | ----
uid|int|请求用户的uid|
sid|int|皮肤id|

**返回结构**
```json
{
  "code": 0,
  "data": {
    "name": "string",
    "url": "string",
    "id": 0
  }
}
```
其中：
* **code**：-2代表sid对应皮肤不存在
* **name**: 皮肤文件名
* **url**：皮肤下载地址url
* **id**：皮肤id
