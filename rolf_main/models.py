from django.db import models
from django.contrib.auth.models import User
import os
import stat
import time
from datetime import datetime,timedelta
import sys
import StringIO
import types
from subprocess import Popen,PIPE
import os.path
import cStringIO
from tempfile import TemporaryFile

from SilverCity import Python,Perl
from django.conf import settings

class Category(models.Model):
    name = models.CharField(max_length=256)

    class Meta:
        ordering = ('name',)

    def get_absolute_url(self):
        return "/category/%d/" % self.id 
    
class Application(models.Model):
    name = models.CharField(max_length=256)
    category = models.ForeignKey(Category)
    
    class Meta:
        order_with_respect_to = "category"

    def get_absolute_url(self):
        return "/application/%d/" % self.id

class Deployment(models.Model):
    name = models.CharField(max_length="256",default="prod")
    application = models.ForeignKey(Application)
    
    class Meta:
        order_with_respect_to = "application"

    def get_absolute_url(self):
        return "/deployment/%d/" % self.id

    def all_categories(self):
        return Category.objects.all()

    def new_push(self,user,comment=""):
        return Push.objects.create(deployment=self,user=user,comment=comment)

    def env(self):
        d = dict(DEPLOYMENT_ID=str(self.id))
        for s in self.setting_set.all():
            d[s.name] = s.value
        return d

    def status(self):
        if self.push_set.count() > 0:
            return self.most_recent_push().status
        else:
            return "unknown"

    def most_recent_push(self):
        return self.push_set.all()[0]
        

class Setting(models.Model):
    deployment = models.ForeignKey(Deployment)
    name = models.CharField(max_length=256)
    value = models.TextField(blank=True,default="")

    class Meta:
        order_with_respect_to = "deployment"

class Recipe(models.Model):
    name = models.CharField(max_length=256,blank=True,default="")
    code = models.TextField(blank=True,default="")
    language = models.CharField(max_length=256,default="python")
    description = models.TextField(blank=True,default="")

    def get_absolute_url(self):
        return "/cookbook/%d/" % self.id

    def code_html(self):
        if self.language == "python":
            g = Python.PythonHTMLGenerator()
            file = StringIO.StringIO()
            g.generate_html(file,self.code)
            return file.getvalue()
        if self.language == "shell":
            first_line = self.code.split('\n')[0]
            if 'python' in first_line:
                g = Python.PythonHTMLGenerator()
                file = StringIO.StringIO()
                g.generate_html(file,self.code)
                return file.getvalue()
            elif 'perl' in first_line:
                g = Perl.PerlHTMLGenerator()
                file = StringIO.StringIO()
                g.generate_html(file,self.code)
                return file.getvalue()
            else:
                g = Perl.PerlHTMLGenerator()
                file = StringIO.StringIO()
                g.generate_html(file,self.code)
                return file.getvalue()

    
class Stage(models.Model):
    name = models.CharField(max_length=256)
    deployment = models.ForeignKey(Deployment)
    recipe = models.ForeignKey(Recipe)
    
    class Meta:
        order_with_respect_to = "deployment"

    def get_absolute_url(self):
        return "/stage/%d/" % self.id

class Push(models.Model):
    user = models.ForeignKey(User)
    deployment = models.ForeignKey(Deployment)
    comment = models.TextField(blank=True,default="")
    start_time = models.DateTimeField(auto_now_add=True)
    end_time = models.DateTimeField(auto_now=True)
    status = models.CharField(max_length=256,default="inprogress")
    rollback_url = models.CharField(max_length=256,blank=True,default="")

    class Meta:
        ordering = ('-start_time',)

    def get_absolute_url(self):
        return "/push/%d/" % self.id

    def run_stage(self,stage_id,rollback_id=""):
        rollback = None
        if rollback_id:
            rollback = Push.objects.get(id=rollback_id)
        stage = Stage.objects.get(id=stage_id)
        pushstage = PushStage.objects.create(push=self,stage=stage)
        pushstage.run(rollback)
        all_stages = list(self.deployment.stage_set.all())
        if pushstage.status == "failed" or pushstage.stage.id == all_stages[-1].id:
            # last stage, so set the push status
            self.status = pushstage.status
            self.end_time = datetime.now()
            self.save()
        return pushstage

    def checkout_dir(self):
        return os.path.join(settings.CHECKOUT_DIR,
                            str(self.deployment.id),"local")

    def env(self):
        d = self.deployment.env()
        d['CWD'] = self.checkout_dir()
        d['CHECKOUT_DIR'] = self.checkout_dir()
        d['PUSH_COMMENT'] = self.comment
        d['PUSH_UNI'] = self.user.username
        d['ROLLBACK_URL'] = self.rollback_url
        d['ROLF_PUSH_ID'] = "%d" % self.id
        return d


class PushStage(models.Model):
    push = models.ForeignKey(Push)
    stage = models.ForeignKey(Stage)
    start_time = models.DateTimeField(auto_now_add=True)
    end_time = models.DateTimeField(auto_now=True)
    status = models.CharField(max_length=256,default="inprogress")

    def setting(self,name):
        env = self.push.env()
        if hasattr(self,'rollback') and self.rollback is not None:
            env['ROLLBACK_URL'] = self.rollback.rollback_url
        return env.get(name,'')

    def run(self,rollback=None):
        """ run the stage's code """
        self.rollback = rollback
        recipe = self.stage.recipe
        if recipe.language == "python":
            self.status = "ok"
            try:
                exec recipe.code in locals(),globals()
            except Exception, e:
                l = Log.objects.create(pushstage=self,command=recipe.code,
                        stdout="",stderr=str(e))
                self.status = "failed"
        else:
            # write to temp file, exec, then clean up
            script_filename = os.path.join(settings.SCRIPT_DIR,"%d.sh" % self.id)
            code = recipe.code
            if not code.startswith("#!"):
                # make sure it has a shebang line
                code = "#!/bin/bash\n" + code
            open(script_filename,"w").write(code)
            os.chmod(script_filename,stat.S_IRWXU|stat.S_IRWXG|stat.S_IROTH)
            try:
                os.makedirs(self.push.checkout_dir())
            except:
                pass
            #TODO: setup timeout
            env = self.push.env()
            if rollback is not None:
                env['ROLLBACK_URL'] = rollback.rollback_url

            stdout_buffer = TemporaryFile()
            stderr_buffer = TemporaryFile()
            
            p = Popen(script_filename,bufsize=1,
                      stdout=stdout_buffer,stderr=stderr_buffer,
                      cwd=self.push.checkout_dir(),
                      env=env,close_fds=True,
                      shell=True)
            ret = p.wait()
            stdout_buffer.seek(0)
            stderr_buffer.seek(0)
            stdout = stdout_buffer.read()
            stderr = stderr_buffer.read()
            stdout_buffer.close()
            stderr_buffer.close()
            l = Log.objects.create(pushstage=self,command=recipe.code,
                                   stdout=stdout,stderr=stderr)
            if ret == 0:
                self.status = "ok"
            else:
                self.status = "failed"
        self.end_time = datetime.now()
        self.save()

    def execute(self,args):
        """ useful function available to recipes """

        stdout_buffer = TemporaryFile()
        stderr_buffer = TemporaryFile()
   
        p = Popen(args,stdout=stdout_buffer,stderr=stderr_buffer,
                  cwd=self.push.checkout_dir(),close_fds=True)
        ret = p.wait()
        stdout_buffer.seek(0)
        stderr_buffer.seek(0)
        stdout = stdout_buffer.read()
        stderr = stderr_buffer.read()
        stdout_buffer.close()
        stderr_buffer.close()
        l = Log.objects.create(pushstage=self,command=" ".join(args),stdout=stdout,stderr=stderr)
        return (ret,stdout,stderr)

    def stdout(self):
        if self.log_set.count() > 0:
            return self.log_set.all()[0].stdout
        else:
            return ""

    def stderr(self):
        if self.log_set.count() > 0:
            return self.log_set.all()[0].stderr
        else:
            return ""


class Log(models.Model):
    pushstage = models.ForeignKey(PushStage)
    command = models.TextField(blank=True,default="")
    stdout = models.TextField(blank=True,default="")
    stderr = models.TextField(blank=True,default="")
    timestamp = models.DateTimeField(auto_now_add=True)
    
    

