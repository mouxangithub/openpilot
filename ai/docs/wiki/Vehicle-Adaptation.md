# Vehicle Adaptation

## 适合谁

- 新车不在支持列表  
- 能开但信号/功能不对  
- 需要指纹 / CAN 草稿（**不会**直接改 opendbc，只生成草稿）  

## 入口

- Web：**适配新车**  
- `op adapt` 或 `/适配新车`  

## 你需要准备

- 车型年款、fork 名称  
- 最好有一条**封闭场地**短路线  
- 丰田/Lexus 部分车型需 SecOC（见 TSK 设置）  

## AI 会做什么

1. 认车与指纹检查  
2. 必要时引导 Cabana / 路线抓 CAN  
3. 生成 **adaptation_drafts/** 草稿  
4. 说明如何验证、如何交给维护者合入  

## 详细方法论

仓库 [VEHICLE_ADAPTATION_GUIDE.md](https://github.com/mouxangithub/ai/blob/main/docs/VEHICLE_ADAPTATION_GUIDE.md)

## Issue 模板

[新车适配 Issue](https://github.com/mouxangithub/ai/issues/new?template=vehicle_adaptation.yml)
