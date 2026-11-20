# 最终UI路径预检查拒绝

formal-browser-v4使用跨工作目录的../011证明路径时，采证器把未规范化路径用作Git archive字典键，与Git规范化键不等，实际退出1，尚未启动HTTP/浏览器。空raw目录保留。run_formal_browser_v2原代码不重写；新v3仅将额外证明路径resolve为规范绝对路径，在formal-browser-v5新目录执行。该拒绝不代表产品或WebGL失败，也不计通过。
