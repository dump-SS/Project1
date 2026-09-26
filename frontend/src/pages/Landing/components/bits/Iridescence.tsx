/**
 * Iridescence —— 源自 React Bits（https://reactbits.dev，MIT + Commons Clause：
 * 产品内可用，禁止打包成组件库转售）。用于页尾亮区背景（2026-09-25 Skyer 指定，
 * 替换原 Grainient）。
 *
 * 本仓改动（逐条；shader 与算法原样保留，只做工程化）：
 * 1. 新增 `staticFrame` —— reduced-motion 下只渲染一帧，不进 rAF 循环；
 * 2. 新增 IntersectionObserver + `visibilitychange` 暂停：离屏 / 切后台停掉渲染
 *    （上游无条件常驻 rAF，页尾在首屏之外时会一直白烧 GPU）；
 * 3. resize 由 window 监听改成 ResizeObserver 观察容器，并在 swizzle 前把渲染
 *    分辨率上限压到 1920（沿用 Threads 的做法：片元里 8 次循环，成本随像素数线性）；
 * 4. props → uniforms 原地同步、不重建 WebGL 上下文（上游把 color/speed/amplitude
 *    放进 effect deps，改一个值就会销毁重建整个上下文并重置时间）；
 * 5. 指针监听只在 hover 设备上注册（触屏无 hover，省一个常驻监听）。
 */
import { useEffect, useRef } from 'react'
import { Renderer, Program, Mesh, Color, Triangle } from 'ogl'

const vertexShader = `
attribute vec2 uv;
attribute vec2 position;

varying vec2 vUv;

void main() {
  vUv = uv;
  gl_Position = vec4(position, 0, 1);
}
`

const fragmentShader = `
precision highp float;

uniform float uTime;
uniform vec3 uColor;
uniform vec3 uResolution;
uniform vec2 uMouse;
uniform float uAmplitude;
uniform float uSpeed;

varying vec2 vUv;

void main() {
  float mr = min(uResolution.x, uResolution.y);
  vec2 uv = (vUv.xy * 2.0 - 1.0) * uResolution.xy / mr;

  uv += (uMouse - vec2(0.5)) * uAmplitude;

  float d = -uTime * 0.5 * uSpeed;
  float a = 0.0;
  for (float i = 0.0; i < 8.0; ++i) {
    a += cos(i - d - a * uv.x);
    d += sin(uv.y * i + a);
  }
  d += uTime * 0.5 * uSpeed;
  vec3 col = vec3(cos(uv * vec2(d, a)) * 0.6 + 0.4, cos(a + d) * 0.5 + 0.5);
  col = cos(col * cos(vec3(d, a, 2.5)) * 0.5 + 0.5) * uColor;
  gl_FragColor = vec4(col, 1.0);
}
`

interface IridescenceProps {
  /** 基色（0–1 线性分量）；shader 里是**乘在**虹彩输出上的，故越亮越接近「亮底」 */
  color?: [number, number, number]
  speed?: number
  amplitude?: number
  /** 指针交互：鼠标位置轻微推移图案（触屏自动不注册） */
  mouseReact?: boolean
  /** reduced-motion：只渲染静止一帧 */
  staticFrame?: boolean
  className?: string
  style?: React.CSSProperties
}

/** 渲染分辨率上限（片元 8 次循环，成本随像素数线性） */
const MAX_RENDER_DIM = 1920

const isHoverCapable = () =>
  typeof window !== 'undefined' && window.matchMedia?.('(hover: hover)').matches

export default function Iridescence({
  color = [1, 1, 1],
  speed = 1.0,
  amplitude = 0.1,
  mouseReact = true,
  staticFrame = false,
  className,
  style,
}: IridescenceProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  /* 最新 props 由渲染循环直接读（改值不重建上下文、不重置时间） */
  const propsRef = useRef({ color, speed, amplitude })
  propsRef.current = { color, speed, amplitude }

  useEffect(() => {
    const container = containerRef.current
    if (!container) return

    const renderer = new Renderer({ alpha: false })
    const gl = renderer.gl
    gl.clearColor(1, 1, 1, 1)

    const geometry = new Triangle(gl)
    const program = new Program(gl, {
      vertex: vertexShader,
      fragment: fragmentShader,
      uniforms: {
        uTime: { value: 0 },
        uColor: { value: new Color(...propsRef.current.color) },
        uResolution: {
          value: new Color(gl.canvas.width, gl.canvas.height, gl.canvas.width / gl.canvas.height),
        },
        uMouse: { value: new Float32Array([0.5, 0.5]) },
        uAmplitude: { value: propsRef.current.amplitude },
        /* 恒为 1：速率改由 uTime 的积分控制，避免改速时相位跳变（见 loop 注释） */
        uSpeed: { value: 1 },
      },
    })
    const mesh = new Mesh(gl, { geometry, program })

    const resize = () => {
      const { clientWidth, clientHeight } = container
      const baseDpr = Math.min(window.devicePixelRatio || 1, 2)
      const longestSide = Math.max(clientWidth, clientHeight) * baseDpr
      const dpr = longestSide > MAX_RENDER_DIM ? (baseDpr * MAX_RENDER_DIM) / longestSide : baseDpr
      renderer.dpr = dpr
      renderer.setSize(clientWidth, clientHeight)
      program.uniforms.uResolution.value.r = gl.canvas.width
      program.uniforms.uResolution.value.g = gl.canvas.height
      program.uniforms.uResolution.value.b = gl.canvas.width / gl.canvas.height
      if (staticFrame) renderer.render({ scene: mesh })
    }
    const ro = new ResizeObserver(resize)
    ro.observe(container)
    resize()

    /* ⚠️ 初始 must be true（fail-safe）：本仓实测 IntersectionObserver 存在漏回调的情况，
       若初始为 false，漏一次「进入视口」回调就会永远不渲（画布空白 = 背景消失）。
       初始为 true 则最坏只是离屏时多渲几帧（GPU 白烧），视觉永远不会缺 */
    let isVisible = true
    let isPageVisible = !document.hidden
    let raf = 0
    let last = 0

    const loop = (t: number) => {
      raf = requestAnimationFrame(loop)
      const dt = last ? Math.min((t - last) / 1000, 0.05) : 0
      last = t
      const p = propsRef.current
      /* 速度用「积分」实现：相位按 dt × speed 累加，shader 里的 uSpeed 恒为 1。
         若改 uSpeed 本身，相位 = 时间 × 速度会在改值那一瞬跳变（图案一顿）；
         积分写法下 speed 变值只改速率、不断相位，可在底页「光变亮」时平滑提速。 */
      program.uniforms.uTime.value += dt * p.speed
      program.uniforms.uAmplitude.value = p.amplitude
      program.uniforms.uColor.value.set(...p.color)
      renderer.render({ scene: mesh })
    }

    const tryStart = () => {
      if (staticFrame) {
        renderer.render({ scene: mesh })
        return
      }
      if (isVisible && isPageVisible && raf === 0) {
        last = 0
        raf = requestAnimationFrame(loop)
      }
    }
    const tryStop = () => {
      if (raf !== 0) {
        cancelAnimationFrame(raf)
        raf = 0
      }
    }

    const io = new IntersectionObserver(
      ([entry]) => {
        isVisible = entry.isIntersecting
        if (isVisible) tryStart()
        else tryStop()
      },
      { threshold: 0 },
    )
    io.observe(container)

    const onVisibility = () => {
      isPageVisible = !document.hidden
      if (isPageVisible) tryStart()
      else tryStop()
    }
    document.addEventListener('visibilitychange', onVisibility)

    const onPointerMove = (e: PointerEvent) => {
      const rect = container.getBoundingClientRect()
      if (!rect.width || !rect.height) return
      const x = (e.clientX - rect.left) / rect.width
      const y = 1 - (e.clientY - rect.top) / rect.height
      program.uniforms.uMouse.value[0] = x
      program.uniforms.uMouse.value[1] = y
    }
    if (mouseReact && isHoverCapable()) container.addEventListener('pointermove', onPointerMove)

    container.appendChild(gl.canvas)
    tryStart()

    return () => {
      tryStop()
      ro.disconnect()
      io.disconnect()
      document.removeEventListener('visibilitychange', onVisibility)
      if (mouseReact) container.removeEventListener('pointermove', onPointerMove)
      if (container.contains(gl.canvas)) container.removeChild(gl.canvas)
      gl.getExtension('WEBGL_lose_context')?.loseContext()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [staticFrame])

  return <div ref={containerRef} className={className} style={style} />
}
