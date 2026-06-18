# 4090 ComfyUI 工作流目錄（NSFW 媒體生成）

所有 ComfyUI **API-format** 工作流都收進這個 repo(版本控管),這樣換 4090 機器時不用重找。
每條 = 一種能力。app(videoGirl)透過 ComfyUI HTTP API（`/prompt`）載入對應 JSON、填參數、送生成。

- ComfyUI 跑在 4090:`http://127.0.0.1:8188`(目前部署 `/home/bygpu/mentorai-comfyui-official`)。
- app 端透過 **Tailscale / autossh 隧道**連到它(同 BreezyVoice 模式),設 `comfyui_base_url`。
- 模型清單見 `models.manifest.json`;換機器用 `provision-4090.sh`。

> 穩定度圖例:🟢 已驗證穩定 · 🟡 可用但未長期驗證 · 🔴 重(吃 VRAM/RAM)

---

## 文生圖 (T2I)
| 工作流 | 模型主檔 | VRAM | 穩定度 |
|---|---|---|---|
| `t2i/zimage-t2i.api.json` | z_image_turbo_bf16 + ae(vae) + qwen_3_4b(text) | 低(~8-12G) | 🟢 主線 |
| `t2i/zimage-t2i-nsfw-washout.json` | Z-Image Turbo + **TaiwanDollLikeness lora** + Perky Tits lora + seedvr2 放大 | 中 | 🟡 NSFW,未長期驗證 |

## 圖生圖 / 局部重繪 / 控制 (I2I)
| 工作流 | 模型 | VRAM | 穩定度 |
|---|---|---|---|
| `i2i/zimage-img2img.api.json` | z_image_turbo_bf16 + ae + qwen_3_4b | 低 | 🟢 主線 |
| `i2i/zimage-inpaint.api.json` | 同上(VAEEncodeForInpaint) | 低 | 🟢 |
| `i2i/zimage-controlnet-union.api.json` | + Z-Image-Turbo-Fun-Controlnet-Union-2.1 | 中 | 🟢 |
| `i2i/zimage-turbo-img2img.json` | z-image-turbo-fp8 變體 | 低 | 🟡 loose,未驗證 |

## 圖生影片 (I2V)
| 工作流 | 模型主檔 | VRAM | 穩定度 |
|---|---|---|---|
| `i2v/wan22-i2v-q5km.api.json` | wan2.2_i2v_high/low_noise_14B **Q5_K_M.gguf** + umt5_xxl(text) + wan_2.1_vae + lightx2v/seko loras | 高 | 🟢 **正式推薦主線** |
| `i2v/wan22-i2v-q4km.api.json` | 同上 **Q4_K_M.gguf** | 中高 | 🟢 省 VRAM 備用 |
| `i2v/ltx23-10eros-q3ks-small.api.json` | **10Eros_v1-Q3_K_S.gguf** + ltx-2.3-22b-dev-fp8 + LTX23_video_vae + gemma_3_12B(text) | 中 | 🟡 10Eros 最小,未長期驗證 |

## 說話影片 / 帶音訊 (Talking, LTX 2.3 10Eros)
| 工作流 | 模型主檔 | VRAM | 穩定度 |
|---|---|---|---|
| `talking/ltx23-10eros-teacher.api.json` | **10Eros_v1_fp8_transformer** + ltx-2.3-22b-dev-fp8 + 上述 LTX 套件 + 音訊 VAE/vocoder | 🔴 很重(RAM) | 🟢 **目前最穩**(但吃太多記憶體) |
| `talking/ltx23-10eros-course30.api.json` | 同上,30 秒課程入口 | 🔴 很重 | 🟡 |

## 影片換人 / Avatar (LongCat)
| 工作流 | 模型 | 備註 | 穩定度 |
|---|---|---|---|
| `avatar/longcat-single.json` | LongCat(模型在 ComfyUI 外的 LongCat repo,非此 JSON 內嵌) | 單段換人入口;需另裝 LongCat | 🟡 |

---

## 自訂節點(custom nodes)需求
這些工作流用到非內建節點,換機器要一併安裝(見 `provision-4090.sh`):
- **ComfyUI-GGUF**(`UnetLoaderGGUF`)— Wan2.2 / LTX GGUF
- **rgthree-comfy**(`Power Lora Loader (rgthree)`)— LTX loras
- **LTXVideo** 節點(`LTXVAudioVAEEncode/Loader` 等)— LTX 2.3 / 10Eros
- ControlNet / Z-Image 相關載入節點(Z-Image Turbo + ControlNet Union)
- LongCat 換人節點(若用 avatar)

## 建議取捨(依你的需求)
- **照片(NSFW)**:Z-Image 線(t2i/i2i)— 輕、快、穩 → videoGirl #10/#11/#25 用這條。
- **短影片**:`wan22-i2v-q5km`(品質)/ `q4km`(省 VRAM)→ #14/#15 用這條。
- **說話/帶音訊**:LTX teacher 最穩但太吃 RAM → 想省資源試 `ltx23-10eros-q3ks-small`(需先驗證)。
- **換人**:LongCat(#15 進階)。
