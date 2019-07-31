import onemsdk
import datetime
import jwt
import pytz
import requests
import string

from ago import human
from hashids import Hashids

from django.contrib.auth.models import User
from django.core.cache import cache
from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.http import HttpResponse, HttpResponseRedirect
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from django.urls import reverse
from django.views.generic import View as _View
from django.shortcuts import get_object_or_404

from onemsdk.schema.v1 import (
    Response, Menu, MenuItem, MenuItemType, Form, FormItemContent, FormItemMenu,
    FormItemContentType, FormItemMenuItem, FormItemMenuItemType, FormMeta
)

from .models import Post


class View(_View):
    @method_decorator(csrf_exempt)
    def dispatch(self, *a, **kw):
        return super(View, self).dispatch(*a, **kw)

    def get_user(self):
        token = self.request.headers.get('Authorization')
        if token is None:
            raise PermissionDenied

        data = jwt.decode(token.replace('Bearer ', ''), key='87654321')
        user, created = User.objects.get_or_create(id=data['sub'])

        return user

    def to_response(self, content):
        response = Response(content=content)

        return HttpResponse(response.json(), content_type='application/json')


class HomeView(View):
    http_method_names = ['get','post', 'put']

    def get(self, request, post_id=None):
        user = self.get_user()
        if user.username == '':
            form_items = [
                FormItemContent(type=FormItemContentType.string,
                                name='username',
                                description='Please choose a username',
                                header='MENU',
                                footer='Send username')
            ]
            content = Form(body=form_items,
                           method='POST',
                           path=reverse('home'),
                           meta=FormMeta(confirmation_needed=False,
                                         completion_status_in_header=False,
                                         completion_status_show=False))
        else:
            menu_items = [
                MenuItem(description='Add post',
                         method='GET',
                         path=reverse('add_post')),
                MenuItem(description='Search',
                         method='GET',
                         path=reverse('search_wizard')),
                MenuItem(description='My posts',
                         method='GET',
                         path=reverse('my_posts'))
            ]
            
            posts = Post.objects.exclude(
                user=self.get_user()
            ).exclude(
                is_private=True
                ).order_by('-created_at').all()[:3]
            if posts:
                for post in posts:
                    menu_items.append(
                        MenuItem(description=u'{}..'.format(post.title[:17]),
                                 method='GET',
                                 path=reverse('post_detail', args=[post.id]))
                    )

            content = Menu(body=menu_items)

        return self.to_response(content)

    def post(self, request):
        user = self.get_user()
        User.objects.filter(id=user.id).update(username=request.POST['username'])
        return HttpResponseRedirect(reverse('home'))


class AddPostView(View):
    http_method_names = ['get', 'post']

    def get(self, request):
        form_items = [
            FormItemContent(type=FormItemContentType.string,
                     name='title',
                     description='Give your new post a title (maximum 64 characters)',
                     header='add',
                     footer='Reply with post title or BACK'),
            FormItemContent(type=FormItemContentType.string,
                     name='description',
                     description='Send post content (max 50 words)',
                     header='add',
                     footer='Reply with post content or BACK'),
            FormItemMenu(body=[FormItemMenuItem(description='Private (share code)',
                                                value='True'),
                               FormItemMenuItem(description='Public (everyone)',
                                                value='False')],
                         name='is_private')
        ]
        form = Form(body=form_items,
                    method='POST',
                    path=reverse('add_post'),
                    meta=FormMeta(confirmation_needed=False,
                                  completion_status_in_header=False,
                                  completion_status_show=False))

        return self.to_response(form)

    def post(self, request):
        now = datetime.datetime.utcnow().replace(tzinfo=pytz.utc)
        expires_at = now + datetime.timedelta(days=14)
        user_id = self.get_user().id

        new_post = Post.objects.create(
            user=self.get_user(),
            title=request.POST['title'],
            description=request.POST['description'],
            is_private=request.POST['is_private'],
            created_at=now,
            expires_at=expires_at,
            views=0,
        )

        hashids = Hashids(salt=str(user_id),
                          alphabet=string.ascii_lowercase + string.digits,
                          min_length=6)
        
        new_post.code = hashids.encode(new_post.id)
        new_post.save()

        cache.set('new_post', True)
        return HttpResponseRedirect(reverse('post_detail', args=[new_post.id]))


class MyPostsListView(View):
    http_method_names = ['get']

    def get(self, request):
        # TODO: later improvement - check for expired posts
        menu_items = []

        if cache.get('post_deleted'):
            menu_items.extend([MenuItem(description='Post successfuly deleted!')])

        posts = Post.objects.filter(user=self.get_user()).order_by('-created_at')
        if posts:
            for post in posts:
                menu_items.append(
                    MenuItem(description=u'{}..'.format(post.title[:15]),
                             method='GET',
                             path=reverse('post_detail', args=[post.id]))
                )
        else:
            menu_items.append(
                MenuItem(description='You currently have no posts.')
            )
        content = Menu(body=menu_items)
        
        return self.to_response(content)


class PostDetailView(View):
    http_method_names = ['get', 'put', 'delete']

    def get(self, request, id):
        post = get_object_or_404(Post, id=id)
        post.views += 1
        post.save()

        menu_items = []
        body_pre = [
            post.description,
            'Author: {}'.format(post.user.username),
            'Expires in: {}'.format(human(post.expires_at)),
            'Code: {}'.format(post.code),
            'Views: {}'.format(post.views)
        ]

        # check to see if we have notifications set in cache for this post
        if cache.get('new_post'):
            body_pre.insert(0, 'Post successfuly created!')
            cache.delete('new_post')
        elif cache.get('post_private'):
            body_pre.insert(0, 'Post marked as private!')
            cache.delete('post_private')
        elif cache.get('post_renewed'):
            body_pre.insert(0, 'Post successfuly renewed!')
            cache.delete('post_renewed')

        menu_items.extend([MenuItem(description=u'\n'.join(body_pre))])

        if post.user == self.get_user():
            # viewing user is the post owner
            menu_items.extend([
                MenuItem(description='Renew',
                         method='PUT',
                         path=reverse('post_detail', args=[post.id]) + '?attr=renew'),
                MenuItem(description='Delete',
                         method='DELETE',
                         path=reverse('post_detail', args=[post.id]))
           ])
            if not post.is_private:
                menu_items.extend([
                    MenuItem(description='Make private',
                             method='PUT',
                             path=reverse('post_detail', args=[post.id]) + '&attr=is_private')
               ])

        else:
             menu_items.extend([
                 MenuItem(description='-- Options under development:'),
                 MenuItem(description='Send message',
                          method='GET',
                          path=reverse('post_detail', args=[post.id])),
                 MenuItem(description='Comments',
                          method='GET',
                          path=reverse('post_detail', args=[post.id]))
            ])

        content = Menu(body=menu_items, header=post.title, footer='Reply MENU')

        return self.to_response(content)

    def put(self, request, id):
        post = get_object_or_404(Post, id=id)                                    

        if request.GET['attr'] == 'is_private':
            post.is_private = True
            cache.set('post_private', True)
        else:
            #request is for renewal
            now = datetime.datetime.utcnow().replace(tzinfo=pytz.utc)
            expires_at = now + datetime.timedelta(days=14)
            post.expires_at = expires_at
            post.save()
            cache.set('post_renewed', True)

        post.save()
        return HttpResponseRedirect(reverse('post_detail', args=[id]))


    def delete(self, request, id):
        post = get_object_or_404(Post, id=id)                                    
        post.delete()
        cache.set('post_deleted', True)
        return HttpResponseRedirect(reverse('my_posts'))


class SearchWizardView(View):
    http_method_names = ['get', 'post']

    def get(self, request):
        form_items = [
            FormItemContent(type=FormItemContentType.string,
                     name='keyword',
                     description='Send code or keyword to search',
                     header='search',
                     footer='Send code or keyword')
        ]
        form = Form(body=form_items,
                    method='POST',
                    path=reverse('search_wizard'),
                    meta=FormMeta(confirmation_needed=False,
                                  completion_status_in_header=False,
                                  completion_status_show=False))

        return self.to_response(form)
    
    def post(self, request):
        keyword = request.POST['keyword']
        # first check if keyword matches a post code
        if len(keyword) == 6:
            post = Post.objects.filter(code=keyword.lower())
            if post:
                return HttpResponseRedirect(reverse('post_detail', args=[post[0].id]))

        # search in titles and post descriptions
        qs1 = Post.objects.filter(title__icontains=keyword).all()
        qs2 = Post.objects.filter(description__icontains=keyword).all()
        posts = qs1 | qs2

        menu_items = []
        if posts:
            if len(posts) == 1:
                return HttpResponseRedirect(reverse('post_detail', args=[posts[0].id]))

            footer = u'Select an option'
            for post in posts:
                menu_items.append(
                    MenuItem(description=u'{}..'.format(post.title[:15]),
                             method='GET',
                             path=reverse('post_detail', args=[post.id]))
                )
        else:
            menu_items.append(
                MenuItem(description='There are no posts matching your keyword.')
            )
            footer = u'Reply MENU'
        content = Menu(body=menu_items, header='search', footer=footer)

        return self.to_response(content)
