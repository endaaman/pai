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

const { Nuxt, Builder } = require('nuxt')

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
    overlays: ['out.png', 'heat_0.png', 'heat_1.png', 'heat_2.png', 'heat_3.png','heat_4.png'],
  },
}


function generateId() {
  return fns.format(new Date(), 'yyyy-MM-dd_HHmmss')
}

function getUploadedPath(id) {
  return pathlib.join(UPLOAD_DIR, id + '.jpg')
}

function getGeneratedDir(id) {
  return pathlib.join(GENERATED_DIR, id)
}

async function doInference(mode, id) {
  switch (mode) {
    case 'camera':
      await exec(`bash scripts/fake.sh ${id}.jpg`)
      break
  }
}

function wait(s) {
  return new Promise(function (r) {
    setTimeout(r, s)
  })
}

class Result {
  join(name) {
    return pathlib.join(GENERATED_DIR, this.mode, this.id, name)
  }
  constructor(mode, id) {
    this.mode = mode
    this.id = id
    const def = MODE_DEFS[mode]
    this.overlays = def.overlays.map((name) => this.join(name))
    this.original = this.join(def.original)
  }
  serialize() {
    return {
      id: this.id,
      original: this.original,
      overlays: this.overlays,
    }
  }
  async validate() {
    const items = [this.original, ...this.overlays]
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
    const ids = await fs.readdir(mode_base)
    for (const id of ids) {
      const path = pathlib.join(mode_base, id)
      if (!(await fs.stat(path)).isDirectory()) {
        continue
      }
      const r = new Result(mode, id)
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
    this.results = null
  }
  watchResults() {
    chokidar.watch(GENERATED_DIR).on('all', (event, path) => {
      consola.log(event, path)
    })
  }
  serialize() {
    return {
      queue: this.queue,
      current: this.current,
      results: this.results,
    }
  }
  pushTask(mode, id) {
    this.queue.push({mode, id})
    this.task = this.task.catch(function(e) {
      consola.log(`ERROR: ${e}`)
    }).then(async () => {
      this.current = this.queue[0]
      const { mode, id } = this.current
      await doInference(mode, id)
      await wait(1)
      await this.reloadResults()
      this.current = null
      this.queue.shift()
      consola.log('DONE:', this.queue)
    })
    consola.log('CUR: ', this.queue)
  }

  async reloadResults() {
    this.results = null
    this.results = await fetchResults()
  }

  async getResults() {
    if (!this.results) {
      await this.reloadResults()
    }
    return this.results
  }
}


const app = new App()

const wss = new WebSocket.Server({ port: WS_PORT })
wss.on('connection', (ws, socket, request) => {
  consola.log('Connected')
  ws.on('message', (message) => {
    // consola.log('received: %s', message)
    ws.send(JSON.stringify(app.serialize()))
  })
})

const koa = new Koa()
config.dev = koa.env !== 'production'
const nuxt = new Nuxt(config)
const router = new Router()
const multer = koaMulter()

router.get('/api/modes', async (ctx, next) => {
  ctx.body = MODE_DEFS.map((m) => m.name)
})

router.get('/api/results', async (ctx, next) => {
  const results = (await app.getResults()).map((r) => r.serialize())
  ctx.body = results
})

router.post(
  '/api/analyze',
  multer.single('image'),
  async (ctx, next) => {
    const { mode } = ctx.request.body
    if (!mode in MODE_DEFS) {
      ctx.throw(400, `Invalid mode: ${mode}`)
      return
    }
    const id = generateId()
    const p = getUploadedPath(id)
    await fs.writeFile(p, ctx.file.buffer)
    app.pushTask(mode, id)
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

router.all('*', (ctx) => {
  ctx.status = 200
  ctx.respond = false
  ctx.req.ctx = ctx
  nuxt.render(ctx.req, ctx.res)
})

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

  koa.listen(API_PORT, HOST)
}

start()
