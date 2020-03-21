const fs =  require('fs').promises
const pathlib = require('path')
const util = require('util')
const childProcess = require('child_process')

// const http = require('http')
const WebSocket = require('ws')
const Koa = require('koa')
const Router = require('@koa/router')
const fns = require('date-fns')
const koaBody = require('koa-body')
const koaMulter = require('@koa/multer')
const koaLogger = require('koa-logger')
const koaSend = require('koa-send')
const consola = require('consola')
const chokidar = require('chokidar')

// const { Nuxt, Builder } = require('nuxt')

const config = require('../nuxt.config.js')
const exec = util.promisify(childProcess.exec)


const WS_PORT = 8081
const API_PORT = 8080
const HOST = '0.0.0.0'
const UPLOAD_DIR = 'uploaded/'
const GENERATED_DIR = 'generated/'

const MODE_DEFS = {
  camera: {
    original: 'org.jpg',
    overlays: [],
  },
  prostate: {
    original: 'org.jpg',
    overlays: [
      { filename: 'out.png', name: 'integrated' },
      { filename: 'heat_0.png', name: 'none'},
      { filename: 'heat_1.png', name: 'benign'},
      { filename: 'heat_2.png', name: 'Gleason 3'},
      { filename: 'heat_3.png', name: 'Gleason 4'},
      { filename: 'heat_4.png', name: 'Gleason 5'},
    ],
  },
}


function generateName() {
  return fns.format(new Date(), 'yyyy-MM-dd_HHmmss')
}

async function putFile(mode, name, buffer) {
  const dir = pathlib.join(UPLOAD_DIR, mode)
  await fs.mkdir(dir, { recursive: true })
  const p =  pathlib.join(dir, name + '.jpg')
  await fs.writeFile(p, buffer)
}

async function doInference(mode, name) {
  switch (mode) {
    case 'camera':
      await exec(`bash scripts/fake.sh '${name}.jpg'`)
      break
  }
}

function wait(s) {
  return new Promise(function (r) {
    setTimeout(r, s)
  })
}

class Result {
  to_path(a) {
    return pathlib.join(GENERATED_DIR, this.mode, this.name, a)
  }
  constructor(mode, name) {
    this.mode = mode
    this.name = name
    const def = MODE_DEFS[mode]
    this.original = { name: 'original',  path: this.to_path(def.original)}
    this.overlays = def.overlays.map((o) => ({ name: o.name, path: this.to_path(o.filename)}))
  }
  serialize() {
    return {
      name: this.name,
      mode: this.mode,
      original: this.original,
      overlays: this.overlays,
    }
    print()
  }
  async validate() {
    const items = [this.original, ...this.overlays.map((o) => o.path)]
    for (const i of items) {
      let s
      try {
        s = await fs.stat(i)
      } catch(e) {
        if (e.code === 'ENOENT') {
          return false
        } else {
          throw e
        }
      }
      if (!s.isFile()) {
        return false
      }
    }
    return true
  }
}

async function fetchResults() {
  const modes = await fs.readdir(GENERATED_DIR)
  const results =[]
  for (const mode of modes) {
    const mode_base = pathlib.join(GENERATED_DIR, mode)
    if (!(await fs.stat(mode_base)).isDirectory()) {
      continue
    }
    const names = await fs.readdir(mode_base)
    for (const name of names) {
      const path = pathlib.join(mode_base, name)
      const stat = await fs.stat(path)
      if (!stat.isDirectory()) {
        continue
      }
      const r = new Result(mode, name)
      if (!await r.validate()) {
        continue
      }
      results.push(r)
    }
  }
  return results
}

class App {
  constructor() {
    this.queue = []
    this.task = Promise.resolve()
    this.current = null
    this.results = []
    this.startWatchingResults()
  }
  startWatchingResults() {
    let isReady = false
    let timer = null
    chokidar.watch(GENERATED_DIR).on('ready', () => {
      isReady = true
    }).on('all', (event, path) => {
      if (!isReady) {
        return
      }
      // debouncing
      if (timer) {
        clearTimeout(timer)
      }
      timer = setTimeout(() => {
        this.loadResults()
        timer = null
      }, 500)
    })
  }
  serialize() {
    const d = {
      queue: this.queue,
      current: this.current,
      results: this.results.map((r) => r.serialize()),
    }
    return d
  }
  async load() {
    await fs.mkdir(GENERATED_DIR, {recursive: true})
    await this.loadResults()
  }
  pushTask(mode, name) {
    this.queue.push({mode, name})
    this.task = this.task.catch(function(e) {
      consola.log(`ERROR: ${e}`)
    }).then(async () => {
      this.current = this.queue[0]
      const { mode, name } = this.current
      await doInference(mode, name)
      await wait(1)
      await this.loadResults()
      this.current = null
      this.queue.shift()
      consola.log('DONE:', this.queue)
    }).catch((e) => {
      console.log('ERROR: ', e)
    })
    consola.log('CUR: ', this.queue)
  }
  async loadResults() {
    this.results = await fetchResults()
  }
  getResults() {
    return this.results
  }
}


const app = new App()

const wss = new WebSocket.Server({ port: WS_PORT })
wss.on('connection', (ws, socket, request) => {
  consola.log('Connected')
  ws.on('message', (message) => {
    ws.send(JSON.stringify(app.serialize()))
  })
})

const koa = new Koa()
config.dev = koa.env !== 'production'
// const nuxt = new Nuxt(config)
const router = new Router()
const multer = koaMulter()

router.get('/api/modes', async (ctx, next) => {
  ctx.body = MODE_DEFS.map((m) => m.name)
})

router.get('/api/results', async (ctx, next) => {
  const results = app.getResults().map((r) => r.serialize())
  ctx.body = results
})

router.get('/api/modes', async (ctx, next) => {
  ctx.body = app.serialize()
})

router.post(
  '/api/analyze',
  multer.single('image'),
  async (ctx, next) => {
    let { mode, name } = ctx.request.body
    if (!mode in MODE_DEFS) {
      ctx.throw(400, `Invalid mode: ${mode}`)
      return
    }
    if (!name) {
      name = generateName()
    }
    await putFile(mode, name, ctx.file.buffer)
    app.pushTask(mode, name)
    ctx.body = app.serialize()
    ctx.status = 201
  }
)

router.get('/generated/(.*)', async ctx => {
  await koaSend(ctx, ctx.params[0], {
    root: GENERATED_DIR,
    immutable: true,
    // maxAge: oneYearMs,
  })
})

// router.all('*', (ctx) => {
//   ctx.status = 200
//   ctx.respond = false
//   ctx.req.ctx = ctx
//   nuxt.render(ctx.req, ctx.res)
// })

koa.use(router.routes())
koa.use(router.allowedMethods())
koa.use(koaLogger())
koa.use(koaBody({ multipart: true }))

async function start() {
  ///* WITH NUXT
  // if (config.dev) {
  //   const builder = new Builder(nuxt)
  //   await builder.build()
  // } else {
  //   await nuxt.ready()
  // }
  await app.load()
  koa.listen(API_PORT, HOST)
}

start()
