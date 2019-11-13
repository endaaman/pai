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
const multer = require('@koa/multer')
const consola = require('consola')
const { Nuxt, Builder } = require('nuxt')

const config = require('../nuxt.config.js')
const exec = util.promisify(childProcess.exec)


const WS_PORT = 8081
const API_PORT = 8080
const HOST = '0.0.0.0'
const UPLOAD_DIR = 'uploaded/'
const GENERATED_DIR = 'generated/'


function generate_id() {
  return fns.format(new Date(), 'yyyy-MM-dd_HHmmss')
}

function get_uploaded_path(id) {
  return pathlib.join(UPLOAD_DIR, id + '.jpg')
}

async function do_inference(id) {
  await exec(`bash scripts/fake.sh ${id}.jpg`)
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
  to_json() {
    return JSON.stringify({
      queue: this.queue,
      current: this.current,
    })
  }
  push_task(id) {
    this.queue.push(id)
    this.task = this.task.catch(function(e) {
      consola.log(`ERROR: ${e}`)
    }).then(async () => {
      this.current = this.queue[0]
      await do_inference(this.current)
      await wait(1)
      this.current = null
      this.queue.shift()
      consola.log('DONE:', this.queue)
    })
    consola.log('CUR: ', this.queue)
  }
}


const koa = new Koa()
config.dev = koa.env !== 'production'

async function start() {
  const nuxt = new Nuxt(config)

  if (config.dev) {
    const builder = new Builder(nuxt)
    await builder.build()
  } else {
    await nuxt.ready()
  }

  const wss = new WebSocket.Server({ port: WS_PORT })
  const router = new Router()
  const upload = multer()

  const app = new App()

  wss.on('connection', (ws, socket, request) => {
    consola.log('Connected')
    ws.on('message', (message) => {
      // consola.log('received: %s', message)
      ws.send(app.to_json())
    })
  })

  router.get('/api/images', async (ctx, next) => {
    consola.log('get images')
    ctx.body = 'images'
  })

  router.post(
    '/api/upload',
    upload.single('image'),
    async (ctx, next) => {
      const id = generate_id()
      const p = get_uploaded_path(id)
      await fs.writeFile(p, ctx.file.buffer)
      app.push_task(id)
      ctx.body = 'up'
      consola.log('wrote: ', p)
    }
  )

  router.all('*', (ctx) => {
    ctx.status = 200
    ctx.respond = false
    ctx.req.ctx = ctx
    nuxt.render(ctx.req, ctx.res)
  })

  koa.use(router.routes())
  koa.use(router.allowedMethods())
  koa.use(koaBody({ multipart: true }))
  koa.listen(API_PORT, HOST)
}

start()
