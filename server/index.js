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
const { Nuxt, Builder } = require('nuxt')

const config = require('../nuxt.config.js')
const exec = util.promisify(childProcess.exec)


const WS_PORT = 8081
const API_PORT = 8080
const HOST = '0.0.0.0'
const UPLOAD_DIR = 'uploaded/'
const GENERATED_DIR = 'generated/'

const MODE = {
  original: 'org.jpg',
  overlays: ['out.png', 'heat_0.png', 'heat_1.png', 'heat_2.png', 'heat_3.png','heat_4.png']
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

async function doInference(id) {
  await exec(`bash scripts/fake.sh ${id}.jpg`)
}

async function getResults() {
  const items = await fs.readdir(GENERATED_DIR)
  const requests =[]
  for (const item of items) {
    const s = await fs.stat(pathlib.join(GENERATED_DIR, item))
    if (s.isDirectory()) {
      requests.push(new Result(item))
    }
  }
  return requests
}


function wait(s) {
  return new Promise(function (r) {
    setTimeout(r, s)
  })
}

class App {
  constructor() {
    this.queue = []
    this.task = Promise.resolve()
    this.current = null
  }
  serialize() {
    return {
      queue: this.queue,
      current: this.current,
    }
  }
  pushTask(id) {
    this.queue.push(id)
    this.task = this.task.catch(function(e) {
      consola.log(`ERROR: ${e}`)
    }).then(async () => {
      this.current = this.queue[0]
      await doInference(this.current)
      await wait(1)
      this.current = null
      this.queue.shift()
      consola.log('DONE:', this.queue)
    })
    consola.log('CUR: ', this.queue)
  }
}


class Result {
  join(name) {
    return pathlib.join('/generated', this.id, name)
  }
  constructor(id) {
    this.id = id
    this.overlays = MODE.overlays.map((name) => this.join(name))
    this.original = this.join(MODE.original)
  }
  serialize() {
    return {
      id: this.id,
      original: this.original,
      overlays: this.overlays,
    }
  }
}

const app = new App()

const wss = new WebSocket.Server({ port: WS_PORT })
wss.on('connection', (ws, socket, request) => {
  consola.log('Connected')
  ws.on('message', (message) => {
    // consola.log('received: %s', message)
    ws.send(app.serialize())
  })
})

const koa = new Koa()
config.dev = koa.env !== 'production'
const nuxt = new Nuxt(config)
const router = new Router()
const multer = koaMulter()

router.get('/api/modes', async (ctx, next) => {
  ctx.body = MODES.map((m) => m.name)
})

router.get('/api/results', async (ctx, next) => {
  const results = (await getResults()).map((r) => r.serialize())
  ctx.body = results
})

router.post(
  '/api/upload',
  multer.single('image'),
  async (ctx, next) => {
    const id = generateId()
    const p = getUploadedPath(id)
    await fs.writeFile(p, ctx.file.buffer)
    app.pushTask(id)
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
  if (config.dev) {
    const builder = new Builder(nuxt)

    await builder.build()
  } else {
    await nuxt.ready()
  }

  koa.listen(API_PORT, HOST)
}

start()
