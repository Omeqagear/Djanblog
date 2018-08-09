from datetime import datetime, timedelta
from django.db import models
from django.contrib.auth.models import User
from django.conf import settings
from django.template.defaultfilters import slugify
from django.core.urlresolvers import reverse

from taggit.managers import TaggableManager
from markupfield.fields import MarkupField
from markupfield.markup import DEFAULT_MARKUP_TYPES


class BlogManager(models.Manager):
    def get_blog(self):
        blogs = self.all()
        if blogs:
            return blogs[0]
        return None


class Blog(models.Model):
    
    title = models.CharField(max_length=100)
    tag_line = models.CharField(max_length=100)
    entries_per_page = models.IntegerField(default=10)
    recents = models.IntegerField(default=5)
    recent_comments = models.IntegerField(default=5)

    objects = BlogManager()

    def __unicode__(self):
        return self.title

    def save(self, *args, **kwargs):

        """There should not be more than one Blog object"""
        if Blog.objects.count() == 1 and not self.id:
            raise Exception("Only one blog object allowed.")
        # Call the "real" save() method.
        super(Blog, self).save(*args, **kwargs)


class BlogPublishedManager(models.Manager):
    use_for_related_fields = True

    def get_queryset(self):
        return super(BlogPublishedManager, self).get_queryset().filter(
            is_published=True,
            publish_date__lte=datetime.now())


class BlogEntry(models.Model):
    
    title = models.CharField(max_length=100)
    slug = models.SlugField(max_length=100)
    text = MarkupField(default_markup_type=getattr(settings,
                                                   'DEFAULT_MARKUP_TYPE',
                                                   'plain'),
                       markup_choices=getattr(settings, "MARKUP_RENDERERS",
                                              DEFAULT_MARKUP_TYPES))
    summary = models.TextField()
    created_on = models.DateTimeField(default=datetime.max, editable=False)
    created_by = models.ForeignKey(User, unique=False)
    is_page = models.BooleanField(default=False)
    is_published = models.BooleanField(default=True)
    publish_date = models.DateTimeField(null=True)
    comments_allowed = models.BooleanField(default=True)
    is_rte = models.BooleanField(default=False)

    meta_keywords = models.TextField(blank=True, null=True)
    meta_description = models.TextField(blank=True, null=True)

    tags = TaggableManager()

    default = models.Manager()
    objects = BlogPublishedManager()

    class Meta:
        ordering = ['-created_on']
        verbose_name_plural = 'Blog entries'

    def __unicode__(self):
        return self.title

    def save(self, *args, **kwargs):
        if self.title is None or self.title == '':
            self.title = _infer_title_or_slug(self.text.raw)

        if self.slug is None or self.slug == '':
            self.slug = slugify(self.title)

        i = 1
        while True:
            created_slug = self.create_slug(self.slug, i)
            slug_count = BlogEntry.objects.filter(slug__exact=created_slug).exclude(pk=self.pk)
            if not slug_count:
                break
            i += 1
        self.slug = created_slug

        if not self.summary:
            self.summary = _generate_summary(self.text.raw)
        if not self.meta_keywords:
            self.meta_keywords = self.summary
        if not self.meta_description:
            self.meta_description = self.summary

        if self.is_published:
            #default value for created_on is datetime.max whose year is 9999
            if self.created_on.year == 9999:
                self.created_on = self.publish_date
        # Call the "real" save() method.
        super(BlogEntry, self).save(*args, **kwargs)

    def create_slug(self, initial_slug, i=1):
        if not i == 1:
            initial_slug += "-%s" % (i,)
        return initial_slug

    def get_absolute_url(self):
        return reverse('blogango_details',
                       kwargs={'year': self.created_on.strftime('%Y'),
                               'month': self.created_on.strftime('%m'),
                               'slug': self.slug})

    def get_edit_url(self):
        return reverse('blogango_admin_entry_edit', args=[self.id])

    def get_num_comments(self):
        cmnt_count = Comment.objects.filter(comment_for=self, is_spam=False).count()
        return cmnt_count

    def get_num_reactions(self):
        reaction_count = Reaction.objects.filter(comment_for=self).count()
        return reaction_count

    # check if the blog have any comments in the last 24 hrs.
    def has_recent_comments(self):
        yesterday = datetime.now()-timedelta(days=1)
        return Comment.objects.filter(
            comment_for=self, is_spam=False, created_on__gt=yesterday
        ).exists()

    # return comments in the last 24 hrs
    def get_recent_comments(self):
        yesterday = datetime.now()-timedelta(days=1)
        cmnts = Comment.objects.filter(
            comment_for=self, is_spam=False, created_on__gt=yesterday
        ).order_by('-created_on')
        return cmnts


class CommentManager(models.Manager):
    def get_queryset(self):
        return super(CommentManager, self).get_queryset().filter(is_public=True)


class BaseComment(models.Model):
    text = models.TextField()
    comment_for = models.ForeignKey(BlogEntry)
    created_on = models.DateTimeField(auto_now_add=True)
    user_name = models.CharField(max_length=100)
    user_url = models.URLField()

    class Meta:
        ordering = ['created_on']
        abstract = True

    def __unicode__(self):
        return self.text


class Comment(BaseComment):
    
    created_by = models.ForeignKey(User, unique=False, blank=True, null=True)
    email_id = models.EmailField()
    is_spam = models.BooleanField(default=False)
    is_public = models.NullBooleanField(null=True, blank=True)
    user_ip = models.IPAddressField(null=True)
    user_agent = models.CharField(max_length=200, default='')

    default = models.Manager()
    objects = CommentManager()

    def save(self, *args, **kwargs):
        if self.is_spam:
            self.is_public = False
        super(Comment, self).save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse('blogango_comment_details', args=[self.id, ])


class Reaction(BaseComment):
    
    reaction_id = models.CharField(max_length=200, primary_key=True)
    source = models.CharField(max_length=200)
    profile_image = models.URLField(blank=True, null=True)


class BlogRoll(models.Model):
    url = models.URLField(unique=True)
    text = models.CharField(max_length=100)
    is_published = models.BooleanField(default=True)

    def __unicode__(self):
        return self.text

    def get_absolute_url(self):
        return self.url


#Helper methods
def _infer_title_or_slug(text):
    return '-'.join(text.split()[:5])


def _generate_summary(text):
    return ' '.join(text.split()[:100])
